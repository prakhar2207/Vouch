# FORMAL INVENTION DISCLOSURE SPECIFICATION

**Filing Jurisdiction:** Indian Patent Office (IPO), Patent Act 1970 (Section 9 / 10)  
**Classification (IPC/CPC):** G06F 16/27 (Distributed consistency), G06Q 20/02 (Bilateral transaction systems), H04L 9/32 (Cryptographic non-repudiation)  
**Title:** A Computer-Implemented Method and Distributed Computing System for Deterministic State Convergence, Reciprocal Semantic Compensation, and Chained Cryptographic Commitments in Intermittently Connected Enterprise Networks  
**Inventors:** Prakhar et al.  
**Filing Date:** October 2026  
**Document Status:** PRIORITY PATENT APPLICATION DRAFT  

---

## 1. Field of the Invention

The present invention relates generally to distributed computing systems, electronic data interchange (EDI), and database replication protocols. More specifically, the invention relates to a computer-implemented method, non-transitory computer-readable storage medium, and distributed computing network for guaranteeing deterministic mathematical state convergence, automatic reciprocal semantic compensation, and bilateral non-repudiation across multi-tenant enterprise resource planning (ERP) nodes operating in intermittently connected, partition-prone telecommunication environments without requiring a centralized consensus coordinator or blockchain network.

---

## 2. Background and Drawbacks of Prior Art

Enterprise accounting systems and business-to-business (B2B) trade networks frequently operate across disparate corporate boundaries. In emerging economies such as India, supply chains face intermittent Internet connectivity, rural network partitions, high-latency wireless telecommunication links, and asymmetric data synchronization conditions.

Existing technological approaches suffer from several severe technical shortcomings:
1. **Last-Write-Wins (LWW) Data Corruption:** Traditional distributed database replication (such as Cassandra, CouchDB, or distributed MySQL/PostgreSQL) utilizes timestamp-based Last-Write-Wins heuristics. When a buyer node and seller node make simultaneous disconnected updates (e.g., seller applies an outbound logistics charge while buyer inspects and rejects defective units upon delivery), the last arriving timestamp unilaterally overwrites the previous write, destroying valid accounting records and creating unresolvable balance sheet discrepancies.
2. **Double-Entry Invariant Violation ($\sum \text{Debits} \ne \sum \text{Credits}$):** Standard distributed text or key-value Conflict-Free Replicated Data Types (CRDTs) allow unconstrained scalar merges. In financial and inventory computing systems, mutations are governed by multi-variable strict conservation laws: every change in asset or expense must be balanced by a reciprocal change in liability, equity, or revenue. Standard CRDT merges violate these fundamental double-entry conservation laws upon partition recovery.
3. **Bandwidth Exhaustion in Document Replication:** Conventional EDI protocols (such as EDIFACT, ASC X12, UBL, and PEPPOL) transmit full-document snapshots (e.g., 5 KB - 50 KB JSON/XML payloads) upon every minor adjustment. In bandwidth-constrained environments, this causes network congestion, timeouts, and battery exhaustion on mobile Edge/PWA devices.
4. **Blockchain / Consensus Scalability Bottlenecks:** Distributed ledger technology (DLT) and blockchains enforce global consensus across all network participants using Proof-of-Work, Proof-of-Stake, or Byzantine Fault Tolerant (PBFT) consensus. For private bilateral B2B commerce, global consensus introduces unnecessary latency (seconds to minutes), high transaction execution costs, and leaks confidential commercial relationship topology to third-party validators.
5. **Vulnerability to Key Extraction and Local Storage Attacks:** Traditional web and mobile applications store private signing keys in browser `localStorage`, session storage, or software cookies, exposing cryptographic credentials to Cross-Site Scripting (XSS) extraction and memory dumping.

There is therefore a critical technical need for an offline-first distributed convergence protocol that maintains strict conservation laws, provides sub-millisecond local processing, achieves 80%+ bandwidth reduction, operates without a central coordinator or blockchain, and enforces hardware-isolated cryptographic non-repudiation.

---

## 3. Summary of the Invention

The present invention solves the above technical problems through three interdependent, mathematically proved architectural mechanisms:

```
+---------------------------------------------------------------------------------------+
|                                  INVENTION OVERVIEW                                   |
|                                                                                       |
|  [NODE A: SELLER CLIENT / PWA]                      [NODE B: BUYER CLIENT / PWA]      |
|  * Non-extractable WebCrypto Ed25519                * Non-extractable WebCrypto       |
|  * IndexedDB Causal DAG Storage                     * IndexedDB Causal DAG Storage    |
|  * Local Double-Entry Projection                    * Local Double-Entry Projection   |
|         \                                                    /                        |
|          \==== (INTERMITTENT / DISCONNECTED NETWORK) =======/                         |
|                                   |                                                   |
|                        [PILLAR 1: CONVERGENCE]                                        |
|              * Causal Directed Acyclic Graph (DAG)                                    |
|              * Join-Semilattice (S, |_|)                                              |
|              * Double-Entry Invariant Guard (\Sum Debits == \Sum Credits)            |
|                                   |                                                   |
|                        [PILLAR 2: COMPENSATION]                                       |
|              * Deterministic Divergence Calculus: C = F(Delta)                        |
|              * Automatic Reciprocal Pair Generation                                   |
|              * (Item Rejection -> Reciprocal Credit Note Created)                     |
|                                   |                                                   |
|                        [PILLAR 3: COMMITMENT]                                         |
|              * 4-Way Merkle Subsystem Roots (O_n, L_n, I_n, T_n)                      |
|              * Chained Bilateral State Commitment (C_n)                               |
|              * Dual Detached Ed25519 Counter-Signatures (\sigma_A, \sigma_B)          |
|                                   |                                                   |
|                        [AUTHORITATIVE LEDGER BRIDGE]                                  |
|              * Host ERP Physical Ledger & Stock Entry Ingestion                       |
|              * Atomic Idempotency Barrier (Zero Duplicate Postings)                   |
+---------------------------------------------------------------------------------------+
```

### Pillar 1: Double-Entry Conflict-Free Replicated Data Type (DE-CRDT) Convergence
The invention models business transactions not as mutable document tables, but as an append-only Causal Directed Acyclic Graph (DAG) $\mathcal{G} = (\mathcal{V}, \mathcal{E})$ of immutable, digitally signed `AccountingOperation` nodes $\mathcal{V}$ interconnected by causal dependency edges $\mathcal{E}$.
The convergence algorithm forms a bounded join-semilattice $(S, \sqcup)$ where the merge operator $\sqcup$ is:
- **Commutative:** $\mathcal{S}_A \sqcup \mathcal{S}_B = \mathcal{S}_B \sqcup \mathcal{S}_A$
- **Associative:** $(\mathcal{S}_A \sqcup \mathcal{S}_B) \sqcup \mathcal{S}_C = \mathcal{S}_A \sqcup (\mathcal{S}_B \sqcup \mathcal{S}_C)$
- **Idempotent:** $\mathcal{S}_A \sqcup \mathcal{S}_A = \mathcal{S}_A$

Operations are topologically ordered using Lamport logical clocks with deterministic node-ID tie breaking. Merged states are verified against strict conservation invariants:
$$\sum_{j} \text{Debit}_j \equiv \sum_{k} \text{Credit}_k \quad \land \quad \text{Stock}_i \ge 0 \quad (\text{or flagged for audit without lossy zero-clamping})$$

### Pillar 2: Deterministic Semantic Reciprocal Compensation Calculus
When concurrent offline operations create semantic discrepancies (e.g., a buyer inspects delivery and rejects 2 units while the seller concurrently records full payment allocation), classical systems fail or overwrite. The invention introduces a deterministic compensation function:
$$C = \mathcal{F}(\Delta)$$
where $\Delta = \mathcal{G}_{\text{seller}} \ominus \mathcal{G}_{\text{buyer}}$ represents the symmetric difference between operation subgraphs.
Both nodes evaluate $\mathcal{F}(\Delta)$ independently across the network partition and derive identical compensating operations (e.g., an atomic reciprocal `CREDIT_NOTE_ISSUED` linked causally to the buyer's `ITEM_REJECTED` node). This guarantees automatic ledger equilibrium without human intervention or central coordinator involvement.

### Pillar 3: 4-Way Merkle Subsystem Roots & Chained Bilateral State Commitments
To establish indisputable legal auditability and tamper-detection without a blockchain, each synchronization epoch evaluates four independent Merkle trees:
1. $O_n$: Merkle root of all causal operations in topological order.
2. $L_n$: Merkle root of the double-entry general ledger state vector.
3. $I_n$: Merkle root of the physical inventory stock ledger.
4. $T_n$: Merkle root of statutory tax liability records.

The nodes compute a chained Cross-Ledger Commitment:
$$C_n = \text{SHA-256}\left(O_n \mathbin{\Vert} L_n \mathbin{\Vert} I_n \mathbin{\Vert} T_n \mathbin{\Vert} C_{n-1}\right)$$
Both counterparty nodes verify $C_n$ and append detached Ed25519 signatures $(\sigma_{\text{seller}}, \sigma_{\text{buyer}})$. The resulting bilateral commitment record proves exact distributed state equality and prevents back-dated tampering.

---

## 4. Detailed Description of the Technical Mechanisms

### 4.1 Canonical Transaction Normalization
Before signature generation, business transaction payloads are projected into a deterministic Canonical Transaction Envelope ($T_{\text{canon}}$). All numeric quantities, monetary rates, tax amounts, and totals are serialized as fixed-point decimal strings formatted to exactly two fractional digits:
$$\text{DecString}(v) = \text{round}(v, 2)$$
Keys are sorted lexicographically according to RFC 8785 principles. The canonical digest is computed via:
$$H_{\text{canon}} = \text{SHA-256}(\text{CanonicalJsonStringify}(T_{\text{canon}}))$$

### 4.2 Hardware Keystore Isolation (`extractable: false`)
On client computing devices (browsers, mobile PWAs), asymmetric Ed25519 root identity keypairs are generated via the W3C Web Cryptography API with the parameter `extractable: false`. The private key is persisted strictly within browser IndexedDB storage as a structured-clone `CryptoKey` object. The private key cannot be exported, extracted as raw bytes, or accessed by client-side JavaScript, eliminating private key leakage via XSS. In enterprise server environments, the driver delegates to hardware security modules (HSM) or Cloud KMS (AWS KMS / GCP Cloud KMS) in a fail-closed architecture with zero software fallback.

### 4.3 Topological Causal DAG Sorting & Invariant Verification
Upon receiving a batch of remote operations $\{\text{op}_1, \dots, \text{op}_k\}$, the local engine performs:
1. **Deduplication:** Filters out operations whose unique IDs already exist in the local operation log (executed in 0.13 microseconds).
2. **Causal Dependency Check:** Verifies that all antecedent operation IDs in `causal_dependencies` are present in the local DAG.
3. **Topological Ordering:** Computes execution order based on logical clock tuple $(\tau_i, \text{replica\_id}_i)$.
4. **Conservation Guard:** Projects debits and credits; if $\sum \text{Debits} \ne \sum \text{Credits}$, the merge is rejected and flagged as a protocol violation.

---

## 5. Measurable Technical Advancement & Empirical Evidence

As documented in official protocol benchmarks (`docs/patent/benchmarks-and-experiments.md`):
1. **89.62% Telecommunication Bandwidth Reduction:**
   - Conventional Full-JSON Transmission: 6,279 bytes per transaction.
   - Vouch Atomic Causal Operation Transmission: 652 bytes per transaction.
   - Saves over 89% in cellular data usage and battery consumption across millions of B2B transactions.
2. **Sub-20 Microsecond Convergence Latency:**
   - CRDT join-semilattice merge and topological resolution executes in **17.54 microseconds** on standard hardware, sustaining throughput exceeding **57,000 transactions/second per CPU core**.
3. **Zero Divergence Across 780 Permutations:**
   - Multi-replica chaotic property fuzzer tests across 3, 5, 8, and 10 nodes under arbitrary network partition topologies proved **0.00% state divergence** and **0 invariant violations**.
4. **Microsecond-Level Tamper & Replay Rejection:**
   - Deduplication / replay rejection: **0.13 microseconds**.
   - Merkle tamper detection: **167.70 microseconds**.

---

## 6. Statement of Claims (Indian Patent Office Orientation)

### WE CLAIM:

1. A computer-implemented method for deterministic distributed state convergence and non-repudiation in an intermittently connected multi-tenant enterprise computing network, the method comprising:
   - generating, at a first computing node via a hardware-isolated cryptographic processor, an asymmetric cryptographic keypair wherein a private key is stored as a non-extractable cryptographic key object within a secure client-side storage vault;
   - recording, during a network partition, one or more local accounting operations in an append-only causal directed acyclic graph (DAG) maintained in non-transitory memory of said first computing node, wherein each accounting operation comprises a unique operation identifier, a logical timestamp, causal dependency pointers, and an immutable operation payload;
   - normalizing said transaction payload into a deterministic canonical transaction format having fixed-point decimal string representations for all numeric values, and calculating a deterministic cryptographic hash thereof;
   - digitally signing said deterministic cryptographic hash using said non-extractable private key to generate a detached digital signature;
   - transmitting, upon restoration of network connectivity, said causal accounting operations to a second computing node across a telecommunication network;
   - merging, at said second computing node, the received accounting operations with a local causal DAG via a join-semilattice operator satisfying commutativity, associativity, and idempotency to establish mathematically identical causal state without central coordinator intervention;
   - validating that the merged state satisfies a double-entry conservation invariant wherein total debits equal total credits; and
   - deriving, from the merged state, four distinct subsystem Merkle roots representing an operation log root, a general ledger state root, an inventory state root, and a statutory tax compliance root, and generating a chained bilateral cross-ledger state commitment countersigned by both said first and second computing nodes.

2. The method of claim 1, further comprising:
   - detecting, upon reconnection, a semantic discrepancy between the operation subgraphs of said first computing node and said second computing node;
   - deterministically calculating, at both nodes independently, a compensating operation function $C = \mathcal{F}(\Delta)$ over the symmetric difference $\Delta$ of said subgraphs; and
   - generating an atomic reciprocal compensating operation pair comprising a credit note operation and a debit note operation causally dependent upon said discrepancy, thereby restoring cross-enterprise equilibrium without manual reconciliation.

3. The method of claim 1, wherein said non-extractable cryptographic key object is generated via a Web Cryptography application programming interface with an extraction parameter set strictly to false, and persisted in client-side IndexedDB storage via structured cloning such that the private key is shielded from JavaScript runtime extraction and cross-site scripting exposure.

4. The method of claim 1, wherein said chained cross-ledger state commitment $C_n$ at epoch $n$ is calculated according to:
   $$C_n = \text{SHA-256}\left(O_n \mathbin{\Vert} L_n \mathbin{\Vert} I_n \mathbin{\Vert} T_n \mathbin{\Vert} C_{n-1}\right)$$
   where $O_n$ is the operation log Merkle root, $L_n$ is the general ledger root, $I_n$ is the inventory root, $T_n$ is the tax root, and $C_{n-1}$ is the commitment from the preceding epoch.

5. The method of claim 1, further comprising:
   - executing an idempotent ledger bridge on an enterprise resource planning database, wherein operations from the converged causal DAG are ingested into authoritative double-entry general ledgers and stock registers under an atomic concurrency lock, preventing duplicate voucher posting across concurrent synchronization requests.

6. The method of claim 1, wherein server-side signing is delegated to an enterprise cloud key management service (KMS) or hardware security module (HSM) operating under a fail-closed security policy, wherein any signing failure or missing hardware credential immediately aborts the transaction without fallback to in-memory software signing.

7. A distributed computing system for deterministic state convergence and bilateral non-repudiation, the system comprising:
   - a first computing node comprising a hardware processor, a network interface, and a non-transitory memory storing a client-side causal DAG of accounting operations and an isolated cryptographic keystore;
   - a second computing node communicatively coupled to said first computing node via an intermittent network;
   - wherein each node is configured to execute instructions causing the nodes to:
     - generate non-extractable asymmetric digital signatures over deterministic fixed-point canonical transaction payloads;
     - execute an append-only join-semilattice merge over causal operations received after a network partition;
     - deterministically calculate reciprocal compensating credit and debit operations for concurrent conflicting operations;
     - derive four-way Merkle subsystem roots and construct a chained, countersigned cross-ledger commitment; and
     - atomically ingest converged transactions into authoritative double-entry relational ledgers.

8. A non-transitory computer-readable storage medium comprising computer-executable instructions that, when executed by one or more processors of a distributed computing system, cause the system to perform the method according to any one of claims 1 to 6.
