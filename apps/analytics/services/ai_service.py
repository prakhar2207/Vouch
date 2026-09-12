import pandas as pd
import numpy as np
try:
    from sklearn.cluster import KMeans
    from sklearn.linear_model import LinearRegression
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
except ImportError:
    KMeans = None
    LinearRegression = None
    ExponentialSmoothing = None
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from apps.accounting.models import Voucher, LedgerEntry
from apps.companies.models import Company

class AnalyticsEngine:
    @staticmethod
    def get_rfm_segments(company: Company):
        """
        Calculates Recency, Frequency, Monetary (RFM) and clusters customers using KMeans from scikit-learn.
        """
        from django.db.models import Max, Count, Sum
        today = timezone.now().date()
        
        party_stats = list(
            Voucher.objects.filter(company=company, voucher_type='SALES', status='POSTED')
            .values('party_ledger__name')
            .annotate(
                last_purchase=Max('voucher_date'),
                frequency=Count('id'),
                monetary=Sum('total_amount'),
            )
        )
        
        if not party_stats:
            return []
            
        rfm_data = []
        for p in party_stats:
            name = p['party_ledger__name'] or 'Unknown'
            last_date = p['last_purchase']
            recency = (today - last_date).days if last_date else 999
            freq = int(p['frequency'] or 0)
            mon = float(p['monetary'] or 0.0)
            rfm_data.append({
                'party_ledger__name': name,
                'recency': max(0, recency),
                'frequency': freq,
                'monetary': round(mon, 2),
            })
            
        rfm = pd.DataFrame(rfm_data)
        
        if len(rfm) < 3 or KMeans is None:
            # Deterministic tiering when <3 records or scikit-learn is unavailable
            mean_monetary = rfm['monetary'].mean()
            def assign_tier(val):
                if val >= mean_monetary * 1.5:
                    return 'High Value / VIP'
                elif val >= mean_monetary * 0.75:
                    return 'Medium Value'
                return 'Low Value'
            rfm['segment'] = rfm['monetary'].apply(assign_tier)
            rfm['cluster'] = 0
            return rfm.to_dict(orient='records')
            
        X = rfm[['recency', 'frequency', 'monetary']].copy()
        
        # Standardize for KMeans
        X_scaled = (X - X.mean()) / (X.std() + 1e-9)
        
        n_clusters = min(3, len(rfm))
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        rfm['cluster'] = kmeans.fit_predict(X_scaled)
        
        # Rank clusters by average monetary value to assign clean names
        monetary_by_cluster = rfm.groupby('cluster')['monetary'].mean().sort_values()
        sorted_cluster_ids = monetary_by_cluster.index.tolist()
        
        tier_names = ['Low Value', 'Medium Value', 'High Value / VIP']
        tier_map = {cluster_id: tier_names[i] for i, cluster_id in enumerate(sorted_cluster_ids)}
        rfm['segment'] = rfm['cluster'].map(tier_map)
        
        return rfm.to_dict(orient='records')

    @staticmethod
    def get_sales_trend(company: Company):
        """
        Calculates daily sales trend line using Linear Regression to classify business growth:
        - Booming (Slope > threshold)
        - Constant (Slope ~ 0)
        - Declining (Slope < -threshold)
        """
        vouchers = Voucher.objects.filter(company=company, voucher_type='SALES', status='POSTED')
        
        if not vouchers.exists():
            return {
                "status": "Constant",
                "slope": 0.0,
                "growth_rate_pct": 0.0,
                "daily_trend": [],
                "summary": "No historical sales data available."
            }

        data = list(vouchers.values('voucher_date').annotate(daily_sales=Sum('total_amount')).order_by('voucher_date'))
        df = pd.DataFrame(data)
        df['voucher_date'] = pd.to_datetime(df['voucher_date'])
        df['daily_sales'] = df['daily_sales'].astype(float)
        
        # Fill date gaps
        df.set_index('voucher_date', inplace=True)
        df = df.resample('D').sum().fillna(0).reset_index()
        
        # Format daily trend for frontend chart
        daily_trend = [
            {
                "date": row['voucher_date'].strftime('%Y-%m-%d'),
                "sales": round(row['daily_sales'], 2)
            }
            for _, row in df.iterrows()
        ]
        
        if len(df) < 2:
            return {
                "status": "Constant",
                "slope": 0.0,
                "growth_rate_pct": 0.0,
                "daily_trend": daily_trend,
                "summary": "Need at least 2 days of data for trend calculation."
            }

        # Linear regression on days
        X = np.arange(len(df)).reshape(-1, 1)
        y = df['daily_sales'].values
        
        if LinearRegression is not None:
            reg = LinearRegression().fit(X, y)
            slope = float(reg.coef_[0])
        else:
            x_flat = np.arange(len(df), dtype=float)
            x_mean = float(np.mean(x_flat))
            y_mean = float(np.mean(y))
            denom = float(np.sum((x_flat - x_mean) ** 2))
            slope = float(np.sum((x_flat - x_mean) * (y - y_mean)) / denom) if denom != 0 else 0.0
        
        avg_sales = float(y.mean()) if y.mean() > 0 else 1.0
        normalized_slope = (slope / avg_sales) * 100.0  # percentage change per day
        
        if normalized_slope > 1.5:
            status = "Booming"
            summary = f"Sales are rapidly increasing (+{round(normalized_slope, 1)}% daily trajectory)."
        elif normalized_slope < -1.5:
            status = "Declining"
            summary = f"Sales are declining ({round(normalized_slope, 1)}% daily trajectory). Attention needed."
        else:
            status = "Constant"
            summary = "Sales trajectory is stable and constant."
            
        return {
            "status": status,
            "slope": round(slope, 2),
            "normalized_slope": round(normalized_slope, 2),
            "average_daily_sales": round(avg_sales, 2),
            "daily_trend": daily_trend,
            "summary": summary
        }

    @staticmethod
    def forecast_sales(company: Company, days: int = 30):
        """
        P1-15: Honest sales forecasting.
        Requires at least 7 distinct active selling days for statistical validity.
        Communicates uncertainty via confidence tiers (HIGH/MEDIUM/LOW).
        Avoids fabricated ±15% fixed margins.
        """
        import datetime
        vouchers = Voucher.objects.filter(company=company, voucher_type='SALES', status='POSTED')
        distinct_days = vouchers.values('voucher_date').distinct().count()

        if distinct_days < 7:
            return {
                "forecast_days": days,
                "projected_total": 0.0,
                "projected_daily_average": 0.0,
                "trend_status": "Insufficient Data",
                "confidence": "LOW",
                "sample_size_days": distinct_days,
                "trend_summary": f"Not enough sales history for a reliable forecast ({distinct_days}/7 active selling days recorded).",
                "daily_forecast": [],
                "historical_daily_average": 0.0
            }

        trend_info = AnalyticsEngine.get_sales_trend(company)
        avg_sales = float(trend_info.get("average_daily_sales", 0.0))
        slope = float(trend_info.get("slope", 0.0))
        status = trend_info.get("status", "Constant")

        confidence = "HIGH" if distinct_days >= 30 else "MEDIUM"

        today = datetime.date.today()
        forecast_list = []
        projected_total = 0.0

        for i in range(1, days + 1):
            future_date = today + datetime.timedelta(days=i)
            base_proj = max(0.0, avg_sales + (slope * (i / 10.0)))
            spread = round(base_proj * 0.10 if confidence == "HIGH" else base_proj * 0.20, 2)
            lower = max(0.0, round(base_proj - spread, 2))
            upper = round(base_proj + spread, 2)
            proj = round(base_proj, 2)
            projected_total += proj

            forecast_list.append({
                "date": future_date.strftime('%Y-%m-%d'),
                "projected_sales": proj,
                "lower_bound": lower,
                "upper_bound": upper
            })

        return {
            "forecast_days": days,
            "projected_total": round(projected_total, 2),
            "projected_daily_average": round(projected_total / max(1, days), 2),
            "trend_status": status,
            "confidence": confidence,
            "sample_size_days": distinct_days,
            "trend_summary": f"{trend_info.get('summary', '')} Confidence: {confidence} based on {distinct_days} days of history.",
            "daily_forecast": forecast_list,
            "historical_daily_average": avg_sales
        }

    @staticmethod
    def get_full_insights(company: Company):
        """
        P1-12 & P1-13: Owner-first dashboard metrics and actionable business alerts.
        Replaces misleading 'Net Position' (sales - purchases) with real-world financial figures:
        Today's Sales, Today's Collections, Money to Collect, Bills to Pay, Cash & Bank, Stock Value.
        """
        from apps.ledgers.models import Ledger
        from apps.inventory.models import Product
        from django.db.models import F, ExpressionWrapper, DecimalField, Q
        import datetime

        today = timezone.now().date()

        # 1. Today's figures
        today_sales = Voucher.objects.filter(
            company=company, voucher_type='SALES', voucher_date=today, status='POSTED'
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')

        today_collections = Voucher.objects.filter(
            company=company, voucher_type='RECEIPT', voucher_date=today, status='POSTED'
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')

        # 2. Cumulative Volumes
        total_sales = Voucher.objects.filter(
            company=company, voucher_type='SALES', status='POSTED'
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')

        total_purchases = Voucher.objects.filter(
            company=company, voucher_type='PURCHASE', status='POSTED'
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')

        sales_count = Voucher.objects.filter(company=company, voucher_type='SALES', status='POSTED').count()
        purchase_count = Voucher.objects.filter(company=company, voucher_type='PURCHASE', status='POSTED').count()

        # 3. Money to Collect (Sundry Debtors / Customer Outstanding)
        debtors_balance = Ledger.objects.filter(
            company=company, group__nature='ASSET', group__name__icontains='Debtor'
        ).aggregate(Sum('current_balance'))['current_balance__sum'] or Decimal('0.00')
        if debtors_balance == Decimal('0.00'):
            debtors_balance = Ledger.objects.filter(
                company=company, ledger_type='PARTY', current_balance__gt=0
            ).aggregate(Sum('current_balance'))['current_balance__sum'] or Decimal('0.00')

        # 4. Bills to Pay (Sundry Creditors / Supplier Outstanding)
        creditors_balance = Ledger.objects.filter(
            company=company, group__nature='LIABILITY', group__name__icontains='Creditor'
        ).aggregate(Sum('current_balance'))['current_balance__sum'] or Decimal('0.00')
        if creditors_balance == Decimal('0.00'):
            neg_parties = Ledger.objects.filter(
                company=company, ledger_type='PARTY', current_balance__lt=0
            ).aggregate(Sum('current_balance'))['current_balance__sum'] or Decimal('0.00')
            creditors_balance = abs(neg_parties)

        # 5. Cash & Bank
        cash_bank = Ledger.objects.filter(
            company=company, ledger_type__in=['CASH', 'BANK']
        ).aggregate(Sum('current_balance'))['current_balance__sum'] or Decimal('0.00')

        # 6. Stock Valuation
        stock_val_expr = ExpressionWrapper(F('stock_quantity') * F('purchase_price'), output_field=DecimalField(max_digits=15, decimal_places=2))
        retail_val_expr = ExpressionWrapper(F('stock_quantity') * F('selling_price'), output_field=DecimalField(max_digits=15, decimal_places=2))

        in_stock_prods = Product.objects.filter(company=company, stock_quantity__gt=0)
        total_stock_value = in_stock_prods.annotate(v=stock_val_expr).aggregate(Sum('v'))['v__sum'] or Decimal('0.00')
        total_retail_value = in_stock_prods.annotate(v=retail_val_expr).aggregate(Sum('v'))['v__sum'] or Decimal('0.00')
        total_stock_qty = in_stock_prods.aggregate(Sum('stock_quantity'))['stock_quantity__sum'] or Decimal('0.00')
        total_in_stock_items = in_stock_prods.count()
        total_catalog_items = Product.objects.filter(company=company).count()

        # 7. Actionable Business Alerts (P2-3)
        alerts = []
        low_stock_prods = Product.objects.filter(company=company, stock_quantity__lte=5, stock_quantity__gte=0, is_active=True)[:4]
        for lp in low_stock_prods:
            alerts.append({
                "type": "LOW_STOCK",
                "severity": "WARNING",
                "message": f"Low Stock: '{lp.name}' has only {lp.stock_quantity} {lp.unit or 'units'} remaining."
            })

        # Overdue Customer Invoices
        overdue_invoices = Voucher.objects.filter(
            company=company, voucher_type='SALES', status='POSTED',
            voucher_date__lt=today - datetime.timedelta(days=30)
        ).select_related('party_ledger').defer('attachment_data', 'attachment_mime')[:3]
        for oi in overdue_invoices:
            alerts.append({
                "type": "OVERDUE_INVOICE",
                "severity": "INFO",
                "message": f"Overdue Bill: Invoice #{oi.voucher_number} for {oi.party_ledger.name if oi.party_ledger else 'Customer'} (₹{oi.total_amount}) is past 30 days."
            })

        rfm_segments = AnalyticsEngine.get_rfm_segments(company)
        trend = AnalyticsEngine.get_sales_trend(company)

        return {
            "business_health": trend["status"],
            "trend_summary": trend["summary"],
            "trend_details": trend,
            "rfm_clusters": rfm_segments,
            "actionable_alerts": alerts,
            "kpis": {
                "today_sales": float(today_sales),
                "today_collections": float(today_collections),
                "money_to_collect": float(debtors_balance),
                "bills_to_pay": float(creditors_balance),
                "cash_and_bank": float(cash_bank),
                "total_sales": float(total_sales),
                "total_purchases": float(total_purchases),
                "sales_vouchers_count": sales_count,
                "purchase_vouchers_count": purchase_count,
                "total_stock_value": float(total_stock_value),
                "total_retail_value": float(total_retail_value),
                "total_stock_qty": float(total_stock_qty),
                "total_in_stock_items": total_in_stock_items,
                "total_catalog_items": total_catalog_items,
            }
        }
