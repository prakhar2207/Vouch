import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.linear_model import LinearRegression
from statsmodels.tsa.holtwinters import ExponentialSmoothing
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
        vouchers = Voucher.objects.filter(company=company, voucher_type='SALES', status='POSTED')
        
        if not vouchers.exists():
            return []
            
        data = list(vouchers.values('party_ledger__name', 'voucher_date', 'total_amount'))
        df = pd.DataFrame(data)
        df['total_amount'] = df['total_amount'].astype(float)
        df['voucher_date'] = pd.to_datetime(df['voucher_date'])
        
        today = pd.to_datetime(timezone.now().date())
        
        # Calculate RFM per customer
        rfm = df.groupby('party_ledger__name').agg({
            'voucher_date': lambda x: (today - x.max()).days, # Recency (days since last purchase)
            'party_ledger__name': 'count',                    # Frequency (number of orders)
            'total_amount': 'sum'                             # Monetary (total spend)
        }).rename(columns={
            'voucher_date': 'recency',
            'party_ledger__name': 'frequency',
            'total_amount': 'monetary'
        }).reset_index()
        
        if len(rfm) < 3:
            rfm['segment'] = 'Standard'
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
        
        reg = LinearRegression().fit(X, y)
        slope = float(reg.coef_[0])
        
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
    def get_full_insights(company: Company):
        """
        Consolidated AI insights endpoint combining RFM clustering, sales trajectory, and KPIs.
        """
        rfm_segments = AnalyticsEngine.get_rfm_segments(company)
        trend = AnalyticsEngine.get_sales_trend(company)
        
        total_sales = Voucher.objects.filter(
            company=company, voucher_type='SALES', status='POSTED'
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
        
        total_purchases = Voucher.objects.filter(
            company=company, voucher_type='PURCHASE', status='POSTED'
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
        
        sales_count = Voucher.objects.filter(company=company, voucher_type='SALES', status='POSTED').count()
        purchase_count = Voucher.objects.filter(company=company, voucher_type='PURCHASE', status='POSTED').count()
        
        from apps.inventory.models import Product
        from django.db.models import F, ExpressionWrapper, DecimalField
        stock_val_expr = ExpressionWrapper(F('stock_quantity') * F('purchase_price'), output_field=DecimalField(max_digits=15, decimal_places=2))
        retail_val_expr = ExpressionWrapper(F('stock_quantity') * F('selling_price'), output_field=DecimalField(max_digits=15, decimal_places=2))
        
        in_stock_prods = Product.objects.filter(company=company, stock_quantity__gt=0)
        total_stock_value = in_stock_prods.annotate(v=stock_val_expr).aggregate(Sum('v'))['v__sum'] or Decimal('0.00')
        total_retail_value = in_stock_prods.annotate(v=retail_val_expr).aggregate(Sum('v'))['v__sum'] or Decimal('0.00')
        total_stock_qty = in_stock_prods.aggregate(Sum('stock_quantity'))['stock_quantity__sum'] or Decimal('0.00')
        total_in_stock_items = in_stock_prods.count()
        total_catalog_items = Product.objects.filter(company=company).count()

        return {
            "business_health": trend["status"],
            "trend_summary": trend["summary"],
            "trend_details": trend,
            "rfm_clusters": rfm_segments,
            "kpis": {
                "total_sales": float(total_sales),
                "total_purchases": float(total_purchases),
                "sales_vouchers_count": sales_count,
                "purchase_vouchers_count": purchase_count,
                "net_position": float(total_sales - total_purchases),
                "total_stock_value": float(total_stock_value),
                "total_retail_value": float(total_retail_value),
                "total_stock_qty": float(total_stock_qty),
                "total_in_stock_items": total_in_stock_items,
                "total_catalog_items": total_catalog_items,
            }
        }
