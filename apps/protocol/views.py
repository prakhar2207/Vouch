import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny

from apps.companies.models import Company
from .sync_service import SyncService, MultiTenantSecurityError
from .handshake import EdiStateMachine, EdiState
import uuid
from .models import ProtocolTransaction, ProtocolOperation, CryptographicCommitment, EdiSession, AuthorizedDevice
from .operation import AccountingOperation
from .bridge import LedgerBridge

logger = logging.getLogger(__name__)

class ProtocolSyncAPIView(APIView):
    """
    2-Way CRDT Synchronization Endpoint.
    Merges client operational logs, runs automated compensation, enforces invariants,
    computes independent Merkle roots, and executes authoritative Ledger Bridge.
    Enforces strict JWT authentication and tenant membership authorization.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        data = request.data
        tx_id = data.get("transaction_id")
        client_replica_id = data.get("client_replica_id", "ANON_CLIENT")
        client_ops = data.get("client_operations", [])
        requested_company_id = data.get("company_id")

        if not tx_id:
            return Response({"error": "transaction_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Multi-Tenant Isolation: Derive company strictly from authenticated user membership
        user = request.user
        company = None
        if getattr(user, 'is_superuser', False):
            if requested_company_id:
                company = Company.objects.filter(id=requested_company_id).first()
            else:
                company = Company.objects.first()
        else:
            if requested_company_id:
                company = Company.objects.filter(id=requested_company_id, users__user=user).first()
                if not company:
                    return Response(
                        {"error": "Access Denied: You do not have membership in the requested company.", "status": "ACCESS_DENIED"},
                        status=status.HTTP_403_FORBIDDEN
                    )
            else:
                user_co = user.companies.select_related('company').first()
                if user_co:
                    company = user_co.company

        if not company:
            return Response(
                {"error": "Access Denied: Authenticated user is not associated with an authorized active company.", "status": "ACCESS_DENIED"},
                status=status.HTTP_403_FORBIDDEN
            )

        # Retrieve existing server operations for this transaction
        server_ops_qs = ProtocolOperation.objects.filter(transaction__transaction_id=tx_id).order_by('logical_timestamp')
        server_operations = []
        for db_op in server_ops_qs:
            server_operations.append(AccountingOperation(
                operation_id=db_op.operation_id,
                transaction_id=tx_id,
                replica_id=db_op.replica_id,
                operation_type=db_op.operation_type,
                payload=db_op.payload,
                logical_timestamp=db_op.logical_timestamp,
                parents=db_op.parents,
                signature=db_op.signature
            ))

        try:
            sync_result = SyncService.process_sync_payload(
                transaction_id=tx_id,
                client_replica_id=client_replica_id,
                client_operations=client_ops,
                server_operations=server_operations,
                authenticated_tenant_id=str(company.id),
                seller_identity=str(company.gstin or company.id),
                buyer_identity=data.get("buyer_identity", "BUYER"),
                canonical_tx_hash=data.get("canonical_tx_hash"),
                verify_signatures=True,
                company=company,
                persist_to_db=True,
                user=user
            )

            res_status = sync_result.get("status")
            if res_status == "SYNC_SUCCESS":
                return Response(sync_result, status=status.HTTP_200_OK)
            elif res_status in ("SYNC_REJECTED", "AWAITING_DEPENDENCIES"):
                return Response(sync_result, status=status.HTTP_400_BAD_REQUEST)
            elif res_status in ("BRIDGE_FAILED", "PERSISTENCE_FAILED"):
                return Response(sync_result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                return Response(sync_result, status=status.HTTP_400_BAD_REQUEST)

        except MultiTenantSecurityError as e:
            return Response({"error": str(e), "status": "ACCESS_DENIED"}, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            logger.error(f"Protocol sync error: {e}", exc_info=True)
            return Response({"error": str(e), "status": "SYNC_ERROR"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProtocolHandshakeAPIView(APIView):
    """
    EDI State Machine Handshake Endpoint.
    Executes 2-phase commit transitions (DISCOVER -> AUTHENTICATE -> NEGOTIATE -> PREPARE -> COMMIT).
    Enforces JWT authentication and tenant boundary checks.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        data = request.data
        session_id = data.get("session_id")
        target_state = data.get("target_state")
        context_data = data.get("context_data", {})

        if not session_id or not target_state:
            return Response({"error": "session_id and target_state are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Boundary check for existing EDI session
        session = EdiSession.objects.filter(session_id=session_id).first()
        if session and not getattr(request.user, 'is_superuser', False):
            user_company_ids = {str(cid) for cid in request.user.companies.values_list('company_id', flat=True)}
            initiator = str(session.initiator_replica_id or "")
            responder = str(session.responder_replica_id or "")
            session_ctx = session.context_data or {}
            src_co = str(session_ctx.get("source_company_id", ""))
            dst_co = str(session_ctx.get("destination_company_id", ""))

            relevant_ids = {initiator, responder, src_co, dst_co} - {""}
            if relevant_ids and not (user_company_ids & relevant_ids):
                user_gstins = set(Company.objects.filter(id__in=user_company_ids).values_list('gstin', flat=True))
                if not (user_gstins & relevant_ids):
                    return Response(
                        {"error": "Access Denied: You are not authorized to participate in this EDI session.", "status": "ACCESS_DENIED"},
                        status=status.HTTP_403_FORBIDDEN
                    )

        try:
            sm = EdiStateMachine(session_id=session_id)
            new_state = sm.transition_to(EdiState(target_state), context_data=context_data)
            return Response({
                "session_id": session_id,
                "current_state": new_state.value,
                "history": sm.session.transition_history if sm.session else []
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ProtocolCommitmentAPIView(APIView):
    """
    Retrieves latest cryptographic commitment and 4-way Merkle state roots.
    Enforces JWT authentication and tenant boundary isolation.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, tx_id, *args, **kwargs):
        commitment = CryptographicCommitment.objects.filter(transaction__transaction_id=tx_id).order_by('-created_at').first()
        if not commitment:
            return Response({"error": "Commitment not found for transaction"}, status=status.HTTP_404_NOT_FOUND)

        # Multi-tenant boundary check: user must belong to source or destination company
        if not getattr(request.user, 'is_superuser', False):
            user_company_ids = {str(cid) for cid in request.user.companies.values_list('company_id', flat=True)}
            user_gstins = set(Company.objects.filter(id__in=user_company_ids).values_list('gstin', flat=True))
            ptx = commitment.transaction
            src_id = str(ptx.source_company_id)
            dst_id = str(ptx.destination_company_id)
            if not (user_company_ids & {src_id, dst_id}) and not (user_gstins & {src_id, dst_id}):
                return Response(
                    {"error": "Access Denied: You are not authorized to view commitments for this transaction.", "status": "ACCESS_DENIED"},
                    status=status.HTTP_403_FORBIDDEN
                )

        return Response({
            "transaction_id": tx_id,
            "commitment_hash": commitment.commitment_hash,
            "operation_state_root": commitment.operation_state_root,
            "previous_commitment_hash": commitment.previous_commitment_hash,
            "created_at": commitment.created_at.isoformat()
        }, status=status.HTTP_200_OK)


class ProtocolDeviceRegistrationAPIView(APIView):
    """
    Cryptographic Device Registration and Authorization Endpoint.
    Binds an offline client device identity (device_id, replica_id) to an enterprise Company,
    records its Ed25519 public key, and enables fail-closed cryptographic sync.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        data = request.data
        device_id = data.get("device_id")
        replica_id = data.get("replica_id")
        public_key_hex = data.get("public_key_hex")
        key_id = data.get("key_id") or f"KID-{uuid.uuid4().hex[:12].upper()}"
        device_name = data.get("device_name", "Browser Client")
        company_id = data.get("company_id")

        if not (device_id and replica_id and public_key_hex):
            return Response(
                {"error": "device_id, replica_id, and public_key_hex are required.", "status": "INVALID_PAYLOAD"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Multi-Tenant isolation check
        user = request.user
        company = None
        if getattr(user, 'is_superuser', False):
            if company_id:
                company = Company.objects.filter(id=company_id).first()
            else:
                company = Company.objects.first()
        else:
            if company_id:
                company = Company.objects.filter(id=company_id, users__user=user).first()
            else:
                user_co = user.companies.select_related('company').first()
                if user_co:
                    company = user_co.company

        if not company:
            return Response(
                {"error": "Access Denied: Authenticated user is not associated with the requested company.", "status": "ACCESS_DENIED"},
                status=status.HTTP_403_FORBIDDEN
            )

        # Register or update AuthorizedDevice
        device, created = AuthorizedDevice.objects.update_or_create(
            device_id=device_id,
            defaults={
                "replica_id": replica_id,
                "company": company,
                "registered_by": user,
                "device_name": device_name,
                "public_key_hex": public_key_hex,
                "key_id": key_id,
                "status": "ACTIVE"
            }
        )

        # Register in in-memory ProtocolKeyManager as well
        from .key_manager import ProtocolKeyManager
        ProtocolKeyManager.get_default().register_public_key(
            key_id=key_id,
            replica_id=replica_id,
            public_key_hex=public_key_hex
        )

        return Response({
            "status": "REGISTERED",
            "device_id": device.device_id,
            "replica_id": device.replica_id,
            "key_id": device.key_id,
            "device_status": device.status,
            "company_id": str(company.id)
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
