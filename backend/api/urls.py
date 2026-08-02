from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)
from .views import (
    RegisterView,
    UserProfileView,
    FarmerListView,
    MilkCollectionViewSet,
    DashboardStatsView,
    GenerateCodeView,
    OTPTokenObtainPairView,
    DeleteAccountView,
    dairy_dashboard,
    link_farmer,
    deactivate_linked_farmer,
    get_linked_farmers,
    search_farmer_by_code,
    record_milk_collection,
    farmer_payable_summary,
    process_payment,
    get_farmer_payment_history,
    notify_pending_payment,
    generate_report,
    QualityRecordViewSet,
    PaymentViewSet,
    FarmerPaymentSummaryView,
    FarmerCollectionCenterSummaryView,
    FarmerBankDetailsView,
    FarmerBankDetailsUpdateView,
    RequestPaymentView,
    current_profile,
    list_notifications,
    mark_notification_read
)

router = DefaultRouter()
router.register(r'collection', MilkCollectionViewSet, basename='milk-collection')
router.register(r'quality', QualityRecordViewSet, basename='quality-record')
router.register(r'payments', PaymentViewSet, basename='payment')

urlpatterns = [
    # Auth Endpoints
    path('generate-code/', GenerateCodeView.as_view(), name='generate-code'),
    path('register/', RegisterView.as_view(), name='api-register'),
    path('token/', OTPTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # User Profile & Directory
    path('profile/', UserProfileView.as_view(), name='user-profile'),
    path('account/delete/', DeleteAccountView.as_view(), name='delete-account'),
    path('farmers/', FarmerListView.as_view(), name='farmer-list'),

    # Dashboard Analytics
    path('dashboard/', DashboardStatsView.as_view(), name='dashboard-stats'),

    # Viewsets (Collection, Quality, Payments)
    path('', include(router.urls)),

    # Farmer Payment Endpoints
    path('farmer/payment-summary/', FarmerPaymentSummaryView.as_view(), name='farmer-payment-summary'),
    path('farmer/collection-center-summary/', FarmerCollectionCenterSummaryView.as_view(), name='farmer-collection-center-summary'),
    path('farmer/bank-details/', FarmerBankDetailsView.as_view(), name='farmer-bank-details'),
    path('farmer/bank-details/<int:pk>/', FarmerBankDetailsUpdateView.as_view(), name='farmer-bank-details-update'),
    path('farmer/request-payment/', RequestPaymentView.as_view(), name='farmer-request-payment'),

    # Custom Dairy Operator Actions
    path('dairy/dashboard/', dairy_dashboard, name='dairy_dashboard'),
    path('dairy/link-farmer/', link_farmer, name='link_farmer'),
    path('current_profile/', current_profile, name='api_current_profile'),
    path('dairy/deactivate-farmer/', deactivate_linked_farmer, name='deactivate_linked_farmer'),
    path('dairy/linked-farmers/', get_linked_farmers, name='get_linked_farmers'),
    path('dairy/search-farmer/', search_farmer_by_code, name='search_farmer_by_code'),
    path('dairy/record-collection/', record_milk_collection, name='record_milk_collection'),
    path('dairy/farmer-payable-summary/<int:farmer_id>/', farmer_payable_summary, name='farmer_payable_summary'),
    path('dairy/process-payment/', process_payment, name='process_payment'),
    path('dairy/payment-history/<int:farmer_id>/', get_farmer_payment_history, name='get_farmer_payment_history'),
    path('dairy/notify-pending-payment/', notify_pending_payment, name='notify_pending_payment'),
    path('dairy/reports/', generate_report, name='generate_report'),

    # Notification Endpoints
    path('notifications/', list_notifications, name='list_notifications'),
    path('notifications/read-all/', mark_notification_read, name='mark_all_read'),
    path('notifications/<int:notification_id>/read/', mark_notification_read, name='mark_notification_read'),
]