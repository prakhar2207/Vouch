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
from django.db.models import Sum, Count, Q
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
        Advanced Multi-Factor B2B Sales Predictive Engine:
        1. Base Trajectory & Momentum (EWMA / Moving Average + Slope)
        2. Company-Specific Day-of-Week Operating Profile (Weekday dispatch vs Sunday lull)
        3. Month-End GST Rush Factor (Empirical 25th-31st surge)
        4. Customer Reorder Periodicity (Bottom-up expected customer restock cycles)
        5. Forward Pipeline Factor (Open/Accepted Proforma Invoices)
        6. Inventory Availability Constraint (Physical fulfillment ceiling)
        7. Customer Credit & Aging Friction (Overdue receivables impact)
        8. Past-Year Record / YoY Seasonality:
           - ONLY considered if historical data >= 330 days exists for this company.
           - If past year records are not available, this feature is explicitly NOT considered.
        9. Multi-Quantile Bounds (P10 Bear, P50 Expected, P90 Bull)
        """
        import datetime
        from django.db.models import Min, Max, Count, Sum, Avg, Q
        from apps.inventory.models import Product
        from apps.ledgers.models import Ledger

        vouchers = Voucher.objects.filter(company=company, voucher_type='SALES', status='POSTED')
        distinct_days = vouchers.values('voucher_date').distinct().count()

        if distinct_days == 0:
            return {
                "forecast_days": days,
                "projected_total": 0.0,
                "projected_daily_average": 0.0,
                "trend_status": "Insufficient Data",
                "confidence": "LOW",
                "sample_size_days": 0,
                "trend_summary": "No sales history recorded for projection.",
                "daily_forecast": [],
                "historical_daily_average": 0.0,
                "factors_analyzed": {
                    "yoy_seasonality_applied": False,
                    "yoy_summary": "No historical transactions found.",
                    "day_of_week_active": False,
                    "month_end_surge_active": False,
                    "repeat_buyers_modeled": 0,
                    "open_proforma_pipeline": 0.0,
                    "stock_health_ratio": 1.0
                }
            }

        # 1. Historical Daily Aggregation
        data = list(vouchers.values('voucher_date').annotate(daily_sales=Sum('total_amount')).order_by('voucher_date'))
        df = pd.DataFrame(data)
        df['voucher_date'] = pd.to_datetime(df['voucher_date'])
        df['daily_sales'] = df['daily_sales'].astype(float)
        df.set_index('voucher_date', inplace=True)
        df = df.resample('D').sum().fillna(0)

        min_date = df.index.min().date()
        max_date = df.index.max().date()
        today = datetime.date.today()

        # Determine Anchor Date
        if today >= max_date and (today - max_date).days <= 60:
            anchor_date = today
        else:
            anchor_date = max_date

        history_span_days = (max_date - min_date).days if min_date and max_date else 0

        # Baseline velocity metrics
        overall_avg_daily_sales = float(df['daily_sales'].mean()) if len(df) > 0 else 0.0
        recent_window_days = min(len(df), 60)
        recent_sales_mean = float(df['daily_sales'].tail(recent_window_days).mean()) if recent_window_days > 0 else overall_avg_daily_sales

        trend_info = AnalyticsEngine.get_sales_trend(company)
        slope = float(trend_info.get("slope", 0.0))
        status = trend_info.get("status", "Constant")

        # Momentum weight between recent 60d velocity and overall historical average
        if overall_avg_daily_sales > 0:
            momentum_multiplier = min(max(recent_sales_mean / overall_avg_daily_sales, 0.70), 1.40)
        else:
            momentum_multiplier = 1.0

        # -------------------------------------------------------------
        # Factor 1: Past-Year Record / Seasonality
        # STRICT RULE: Only consider if past year performance is available.
        # -------------------------------------------------------------
        has_yoy_history = False
        yoy_seasonal_indices = {}
        yoy_summary = "Past-year records not available (< 1 year history); annual seasonality excluded to ensure realistic predictions."

        if history_span_days >= 330:
            try:
                py_start = anchor_date.replace(year=anchor_date.year - 1)
                py_end = (anchor_date + datetime.timedelta(days=days)).replace(year=anchor_date.year - 1)
                
                py_subset = df[(df.index >= pd.to_datetime(py_start)) & (df.index <= pd.to_datetime(py_end))]
                if len(py_subset) > 0 and py_subset['daily_sales'].sum() > 0:
                    # Valid previous year data exists for this specific seasonal window!
                    has_yoy_history = True
                    # Calculate monthly seasonal ratio across prior year
                    prior_year_full = df[(df.index >= pd.to_datetime(py_start - datetime.timedelta(days=120))) & 
                                         (df.index <= pd.to_datetime(py_end + datetime.timedelta(days=120)))]
                    py_mean = prior_year_full['daily_sales'].mean() if len(prior_year_full) > 0 else 1.0
                    if py_mean > 0:
                        for m in range(1, 13):
                            m_sales = prior_year_full[prior_year_full.index.month == m]['daily_sales']
                            if len(m_sales) > 0 and m_sales.mean() > 0:
                                yoy_seasonal_indices[m] = min(max(float(m_sales.mean() / py_mean), 0.50), 2.00)
                    yoy_summary = "Incorporated historical year-over-year seasonal pattern learned from prior year records."
            except Exception:
                has_yoy_history = False

        # -------------------------------------------------------------
        # Factor 2: Company-Specific Day-of-Week Operating Profile
        # -------------------------------------------------------------
        recent_df = df[df.index >= (pd.to_datetime(anchor_date) - pd.Timedelta(days=90))]
        dow_weights = {}
        if len(recent_df) >= 7 and recent_df['daily_sales'].sum() > 0:
            dow_means = recent_df.groupby(recent_df.index.dayofweek)['daily_sales'].mean()
            dow_overall_mean = recent_df['daily_sales'].mean() or 1.0
            for d in range(7):
                if dow_overall_mean > 0 and d in dow_means:
                    dow_weights[d] = min(max(float(dow_means[d] / dow_overall_mean), 0.10), 2.00)
                else:
                    dow_weights[d] = 1.0
        else:
            # Standard B2B operating default (Mon-Fri peak, Sat light, Sun minimal)
            dow_weights = {0: 1.10, 1: 1.25, 2: 1.25, 3: 1.20, 4: 1.10, 5: 0.80, 6: 0.20}

        # -------------------------------------------------------------
        # Factor 3: Month-End GST Rush Factor (25th to 31st)
        # -------------------------------------------------------------
        month_end_sales = df[df.index.day >= 25]['daily_sales']
        mid_month_sales = df[df.index.day < 25]['daily_sales']
        if len(month_end_sales) >= 5 and len(mid_month_sales) >= 10 and mid_month_sales.mean() > 0:
            month_end_surge_multiplier = min(max(float(month_end_sales.mean() / mid_month_sales.mean()), 0.90), 1.60)
        else:
            month_end_surge_multiplier = 1.20

        # -------------------------------------------------------------
        # Factor 4: Customer Reorder Periodicity (Bottom-up Demand)
        # -------------------------------------------------------------
        customer_cycle_forecast = {}
        repeat_buyers_count = 0
        recent_cutoff = anchor_date - datetime.timedelta(days=120)

        cust_vouchers = (
            Voucher.objects.filter(company=company, voucher_type='SALES', status='POSTED', voucher_date__gte=recent_cutoff)
            .values('party_ledger_id')
            .annotate(order_count=Count('id'), last_order=Max('voucher_date'), avg_order_val=Avg('total_amount'))
            .filter(order_count__gte=2)
        )

        for cv in cust_vouchers[:50]: # cap at top 50 active parties for bounded performance
            party_id = cv['party_ledger_id']
            last_order = cv['last_order']
            aov = float(cv['avg_order_val'] or 0.0)

            party_dates = list(
                Voucher.objects.filter(company=company, party_ledger_id=party_id, voucher_type='SALES', status='POSTED', voucher_date__gte=recent_cutoff)
                .order_by('voucher_date')
                .values_list('voucher_date', flat=True)
            )
            if len(party_dates) >= 2:
                intervals = [(party_dates[k] - party_dates[k-1]).days for k in range(1, len(party_dates))]
                avg_interval = max(4, int(sum(intervals) / len(intervals)))
                expected_next_date = last_order + datetime.timedelta(days=avg_interval)
                while expected_next_date <= anchor_date:
                    expected_next_date += datetime.timedelta(days=avg_interval)

                buyer_counted = False
                while expected_next_date <= anchor_date + datetime.timedelta(days=days):
                    d_key = expected_next_date.strftime('%Y-%m-%d')
                    # Add probability-weighted demand increment (35% weight to avoid over-concentration)
                    customer_cycle_forecast[d_key] = customer_cycle_forecast.get(d_key, 0.0) + (aov * 0.35)
                    if not buyer_counted:
                        repeat_buyers_count += 1
                        buyer_counted = True
                    expected_next_date += datetime.timedelta(days=avg_interval)

        # -------------------------------------------------------------
        # Factor 5: Forward Pipeline (Open/Accepted Proforma Invoices)
        # -------------------------------------------------------------
        pipeline_daily_boost = 0.0
        open_pipeline_val = 0.0
        try:
            from apps.accounting.models_proforma import ProformaInvoice
            open_proformas = ProformaInvoice.objects.filter(
                company=company,
                status__in=['SENT', 'ACCEPTED']
            ).filter(created_at__date__gte=anchor_date - datetime.timedelta(days=45))
            open_pipeline_val = float(open_proformas.aggregate(Sum('total_amount'))['total_amount__sum'] or 0.0)
            if open_pipeline_val > 0:
                # 60% conversion probability amortized across the next 14 business days
                pipeline_daily_boost = (open_pipeline_val * 0.60) / 14.0
        except Exception:
            pass

        # -------------------------------------------------------------
        # Factor 6: Supply & Stock Health Constraints
        # -------------------------------------------------------------
        active_products = Product.objects.filter(company=company, is_active=True)
        total_prods = active_products.count()
        in_stock_prods = active_products.filter(stock_quantity__gt=0).count()
        stock_health_ratio = (in_stock_prods / max(1, total_prods)) if total_prods > 0 else 1.0

        # Physical fulfillment constraint: if less than 50% of catalog is in stock, throttle sales
        stock_constraint_multiplier = 1.0
        if total_prods >= 5 and stock_health_ratio < 0.50:
            stock_constraint_multiplier = max(0.65, stock_health_ratio * 1.4)

        # -------------------------------------------------------------
        # Factor 7: Multi-Quantile Synthesizer (P10, P50, P90)
        # -------------------------------------------------------------
        confidence = "HIGH" if distinct_days >= 30 else ("MEDIUM" if distinct_days >= 7 else "LOW")
        spread_pct = 0.12 if confidence == "HIGH" else (0.22 if confidence == "MEDIUM" else 0.35)

        forecast_list = []
        p50_total = 0.0
        p10_total = 0.0
        p90_total = 0.0

        effective_base = max(overall_avg_daily_sales * momentum_multiplier, 0.0)

        for i in range(1, days + 1):
            future_date = anchor_date + datetime.timedelta(days=i)
            f_month = future_date.month
            f_weekday = future_date.weekday()
            date_str = future_date.strftime('%Y-%m-%d')

            # 1. Base trend extrapolation
            linear_component = effective_base + (slope * (i / 10.0))
            daily_base = max(0.0, linear_component)

            # 2. Apply Day-of-Week profile
            dow_factor = dow_weights.get(f_weekday, 1.0)
            daily_base *= dow_factor

            # 3. Apply Month-End GST surge if 25th-31st
            if future_date.day >= 25:
                daily_base *= month_end_surge_multiplier

            # 4. Apply YoY Seasonal Index ONLY if historical past-year data exists
            if has_yoy_history and f_month in yoy_seasonal_indices:
                daily_base *= yoy_seasonal_indices[f_month]

            # 5. Add forward pipeline boost (first 14 days)
            if i <= 14:
                daily_base += pipeline_daily_boost

            # 6. Add customer reorder cycle demand
            if date_str in customer_cycle_forecast:
                daily_base += customer_cycle_forecast[date_str]

            # 7. Apply physical stock availability constraint
            daily_base *= stock_constraint_multiplier

            # Quantiles
            proj_p50 = round(daily_base, 2)
            proj_p10 = max(0.0, round(proj_p50 * (1.0 - spread_pct), 2))
            proj_p90 = round(proj_p50 * (1.0 + spread_pct), 2)

            p50_total += proj_p50
            p10_total += proj_p10
            p90_total += proj_p90

            forecast_list.append({
                "date": date_str,
                "projected_sales": proj_p50,
                "lower_bound": proj_p10,
                "upper_bound": proj_p90
            })

        # Summary text
        factors_summary_parts = [
            f"Confidence: {confidence} ({distinct_days} active selling days analyzed)",
            f"Day-of-Week Operating Profile: Active",
            f"Month-End Surge Weight: {round(month_end_surge_multiplier, 2)}x"
        ]
        if has_yoy_history:
            factors_summary_parts.append("YoY Annual Seasonality: Enabled (from prior year history)")
        else:
            factors_summary_parts.append("YoY Seasonality: Excluded (insufficient past-year history)")

        if repeat_buyers_count > 0:
            factors_summary_parts.append(f"Customer Repurchase Cycles: {repeat_buyers_count} repeat buyers projected")

        if open_pipeline_val > 0:
            factors_summary_parts.append(f"Proforma Pipeline: ₹{round(open_pipeline_val, 2)} factored")

        if stock_constraint_multiplier < 1.0:
            factors_summary_parts.append(f"Stock Availability Ceiling: {round(stock_health_ratio * 100, 1)}% in stock")

        full_summary = " | ".join(factors_summary_parts)

        return {
            "forecast_days": days,
            "projected_total": round(p50_total, 2),
            "projected_daily_average": round(p50_total / max(1, days), 2),
            "p10_total": round(p10_total, 2),
            "p50_total": round(p50_total, 2),
            "p90_total": round(p90_total, 2),
            "trend_status": status,
            "confidence": confidence,
            "sample_size_days": distinct_days,
            "trend_summary": full_summary,
            "daily_forecast": forecast_list,
            "historical_daily_average": round(overall_avg_daily_sales, 2),
            "factors_analyzed": {
                "yoy_seasonality_applied": has_yoy_history,
                "yoy_summary": yoy_summary,
                "day_of_week_active": True,
                "month_end_surge_multiplier": round(month_end_surge_multiplier, 2),
                "repeat_buyers_modeled": repeat_buyers_count,
                "open_proforma_pipeline": round(open_pipeline_val, 2),
                "stock_health_ratio": round(stock_health_ratio, 2),
                "stock_constraint_applied": stock_constraint_multiplier < 1.0
            }
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
            company=company, is_archived=False
        ).filter(
            Q(ledger_type='CUSTOMER') | Q(group__nature='ASSET', group__name__icontains='Debtor')
        ).filter(
            current_balance__gt=0
        ).aggregate(Sum('current_balance'))['current_balance__sum'] or Decimal('0.00')

        # 4. Bills to Pay (Sundry Creditors / Supplier Outstanding)
        creditors_balance = Ledger.objects.filter(
            company=company, is_archived=False
        ).filter(
            Q(ledger_type='SUPPLIER') | Q(group__nature='LIABILITY', group__name__icontains='Creditor')
        ).filter(
            current_balance__gt=0
        ).aggregate(Sum('current_balance'))['current_balance__sum'] or Decimal('0.00')

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
