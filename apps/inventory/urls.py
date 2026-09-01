from django.urls import path
from .views import ProductListView, ProductCategoryListView, ProductDetailView, WarehouseListView, ProductCategoryDetailView

urlpatterns = [
    path('products/<uuid:company_id>/', ProductListView.as_view(), name='product_list'),
    path('products/<uuid:company_id>/<uuid:product_id>/', ProductDetailView.as_view(), name='product_detail'),
    path('categories/<uuid:company_id>/', ProductCategoryListView.as_view(), name='category_list'),
    path('categories/<uuid:company_id>/<uuid:category_id>/', ProductCategoryDetailView.as_view(), name='category_detail'),
    path('warehouses/<uuid:company_id>/', WarehouseListView.as_view(), name='warehouse_list'),
]
