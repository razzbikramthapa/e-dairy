from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    Profile,
    DairyOperator,
    LinkedFarmer,
    MilkCollection,
    Payment,
    PaymentRequest,
    Notification,
)


def create_user(username, role="farmer", first_name="", last_name="", phone=None, dairy_name=None):
    """Create a user with a role profile (and DairyOperator for agents)."""
    phone = phone or username
    user = User.objects.create_user(
        username=username,
        password="testpass",
        first_name=first_name,
        last_name=last_name,
        email=f"{username}@test.com",
    )
    Profile.objects.create(
        user=user,
        role=role,
        phone=phone,
        address="Kathmandu",
    )
    if role == "agent":
        DairyOperator.objects.create(
            user=user,
            dairy_name=dairy_name or f"{username} Dairy",
            registration_no=f"REG-{username}",
            phone=phone,
            address="Kathmandu",
        )
    return user


def create_collection(farmer, operator, quantity=10.00, fat=4.00, snf=8.00, session="morning"):
    """Create a milk collection; rate = (fat*6)+(snf*4), amount = quantity * rate."""
    return MilkCollection.objects.create(
        farmer=farmer,
        collected_by=operator,
        session=session,
        quantity=Decimal(str(quantity)),
        fat=Decimal(str(fat)),
        snf=Decimal(str(snf)),
    )


def create_paid_payment(farmer, operator, total_amount, paid_amount=None, deductions=0):
    """Create a fully-paid Payment record."""
    paid_amount = total_amount if paid_amount is None else paid_amount
    return Payment.objects.create(
        farmer=farmer,
        dairy_operator=operator,
        total_amount=Decimal(str(total_amount)),
        paid_amount=Decimal(str(paid_amount)),
        deductions=Decimal(str(deductions)),
        payment_status="paid",
        payment_method="cash",
    )


class PaymentTestMixin:
    def setUp(self):
        self.agent = create_user("agent_dev", role="agent", dairy_name="Sample Dairy")
        self.farmer = create_user("farmer_one", role="farmer", first_name="Ram", last_name="Thapa")
        self.other_farmer = create_user("farmer_two", role="farmer", first_name="Sita", last_name="Rai")

    def link_farmer(self, farmer=None):
        farmer = farmer or self.farmer
        return LinkedFarmer.objects.create(dairy_operator=self.agent, farmer=farmer, is_active=True)

    def auth(self, user=None):
        self.client.force_authenticate(user=user or self.agent)

    @staticmethod
    def payment_payload(farmer, total_amount, paid_amount=None, **overrides):
        def money(value):
            return f"{Decimal(str(value)):.2f}"

        payload = {
            "farmer": farmer.id,
            "total_amount": money(total_amount),
            "paid_amount": money(paid_amount if paid_amount is not None else total_amount),
            "deductions": "0.00",
            "payment_status": "paid",
            "payment_method": "cash",
        }
        payload.update(overrides)
        return payload


class PayoutProcessPaymentTests(PaymentTestMixin, APITestCase):
    """Tests for POST /api/dairy/process-payment/ (payouts)."""

    def test_process_cash_payment_creates_payment(self):
        self.auth()
        collection = create_collection(self.farmer, self.agent)
        amount = collection.amount

        response = self.client.post("/api/dairy/process-payment/", self.payment_payload(self.farmer, amount), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        payment = Payment.objects.get(farmer=self.farmer, dairy_operator=self.agent)
        self.assertEqual(payment.total_amount, amount)
        self.assertEqual(payment.paid_amount, amount)
        self.assertEqual(payment.pending_amount, Decimal("0.00"))
        self.assertEqual(payment.payment_status, "paid")

    def test_process_payment_calculates_pending_amount(self):
        self.auth()
        collection = create_collection(self.farmer, self.agent, quantity=10.00)
        amount = collection.amount

        response = self.client.post(
            "/api/dairy/process-payment/",
            self.payment_payload(self.farmer, amount, paid_amount="100.00"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        payment = Payment.objects.get(farmer=self.farmer, dairy_operator=self.agent)
        self.assertEqual(payment.pending_amount, amount - Decimal("100.00"))

    def test_process_bank_transfer_requires_bank_details(self):
        self.auth()
        response = self.client.post(
            "/api/dairy/process-payment/",
            self.payment_payload(self.farmer, "100.00", payment_method="bank_transfer"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("bank", response.data["detail"].lower())
        self.assertFalse(Payment.objects.exists())

    def test_process_paid_payment_approves_pending_requests(self):
        self.auth()
        self.link_farmer()
        collection = create_collection(self.farmer, self.agent)
        PaymentRequest.objects.create(
            farmer=self.farmer, dairy_operator=self.agent, amount_requested=collection.amount
        )

        response = self.client.post(
            "/api/dairy/process-payment/",
            self.payment_payload(self.farmer, collection.amount),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(
            PaymentRequest.objects.get(farmer=self.farmer).status,
            "approved",
        )

    def test_process_paid_payment_notifies_farmer(self):
        self.auth()
        collection = create_collection(self.farmer, self.agent)

        response = self.client.post(
            "/api/dairy/process-payment/",
            self.payment_payload(self.farmer, collection.amount),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(
            Notification.objects.filter(recipient=self.farmer, notification_type="payment_received").exists()
        )

    def test_process_payment_requires_valid_data(self):
        self.auth()
        response = self.client.post(
            "/api/dairy/process-payment/",
            {"farmer": self.farmer.id, "payment_method": "cash"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("total_amount", response.data)


class PaymentsViewSetTests(PaymentTestMixin, APITestCase):
    """Tests for /api/payments/ viewset."""

    def test_agent_creates_payment_via_viewset(self):
        self.auth()
        collection = create_collection(self.farmer, self.agent)

        response = self.client.post("/api/payments/", self.payment_payload(self.farmer, collection.amount), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(response.data["pending_amount"], "0.00")

    def test_agent_sees_own_payments_only(self):
        self.auth()
        create_paid_payment(self.farmer, self.agent, total_amount=560)
        other_agent = create_user("agent_two", role="agent")

        response = self.client.get("/api/payments/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        self.client.force_authenticate(user=other_agent)
        response = self.client.get("/api/payments/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_farmer_sees_only_own_payments(self):
        self.auth()
        create_paid_payment(self.farmer, self.agent, total_amount=560)

        self.client.force_authenticate(user=self.farmer)
        response = self.client.get("/api/payments/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        self.client.force_authenticate(user=self.other_farmer)
        response = self.client.get("/api/payments/")
        self.assertEqual(len(response.data), 0)

    def test_payment_pending_amount_auto_calculated(self):
        payment = Payment.objects.create(
            farmer=self.farmer,
            dairy_operator=self.agent,
            total_amount=Decimal("500.00"),
            paid_amount=Decimal("200.00"),
            deductions=Decimal("50.00"),
            payment_status="paid",
        )
        self.assertEqual(payment.pending_amount, Decimal("250.00"))

    def test_filter_payments_by_status(self):
        self.auth()
        create_paid_payment(self.farmer, self.agent, total_amount=560)
        Payment.objects.create(
            farmer=self.farmer,
            dairy_operator=self.agent,
            total_amount=Decimal("100.00"),
            paid_amount=Decimal("0.00"),
            payment_status="pending",
        )

        response = self.client.get("/api/payments/?status=pending")
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["payment_status"], "pending")

    def test_get_farmer_payment_history(self):
        self.auth()
        create_paid_payment(self.farmer, self.agent, total_amount=560)
        response = self.client.get(f"/api/dairy/payment-history/{self.farmer.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_farmer_payment_summary(self):
        self.auth()
        create_collection(self.farmer, self.agent, quantity=10.00)
        create_paid_payment(self.farmer, self.agent, total_amount=200)

        self.client.force_authenticate(user=self.farmer)
        response = self.client.get("/api/farmer/payment-summary/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_earned"], 560.0)
        self.assertEqual(response.data["total_paid"], 200.0)
        self.assertEqual(response.data["pending_balance"], 360.0)


class PendingPaymentTests(PaymentTestMixin, APITestCase):
    """Tests for pending balances, deactivation, dashboard and reports."""

    def test_deactivate_blocked_when_pending_balance(self):
        self.auth()
        link = self.link_farmer()
        create_collection(self.farmer, self.agent, quantity=10.00)

        response = self.client.post("/api/dairy/deactivate-farmer/", {"farmer_id": self.farmer.id}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        link.refresh_from_db()
        self.assertTrue(link.is_active)

    def test_deactivate_blocked_when_unsettled_pending_payment(self):
        self.auth()
        link = self.link_farmer()
        create_collection(self.farmer, self.agent, quantity=10.00)
        Payment.objects.create(
            farmer=self.farmer,
            dairy_operator=self.agent,
            total_amount=Decimal("560.00"),
            paid_amount=Decimal("300.00"),
            payment_status="pending",
        )

        response = self.client.post("/api/dairy/deactivate-farmer/", {"farmer_id": self.farmer.id}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        link.refresh_from_db()
        self.assertTrue(link.is_active)

    def test_deactivate_success_when_settled(self):
        self.auth()
        link = self.link_farmer()
        collection = create_collection(self.farmer, self.agent, quantity=10.00)
        create_paid_payment(self.farmer, self.agent, total_amount=collection.amount)

        response = self.client.post("/api/dairy/deactivate-farmer/", {"farmer_id": self.farmer.id}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        link.refresh_from_db()
        self.assertFalse(link.is_active)

    def test_deactivate_resolves_pending_payment_requests(self):
        self.auth()
        link = self.link_farmer()
        collection = create_collection(self.farmer, self.agent, quantity=10.00)
        create_paid_payment(self.farmer, self.agent, total_amount=collection.amount)
        PaymentRequest.objects.create(
            farmer=self.farmer, dairy_operator=self.agent, amount_requested=collection.amount
        )

        response = self.client.post("/api/dairy/deactivate-farmer/", {"farmer_id": self.farmer.id}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(PaymentRequest.objects.get(farmer=self.farmer).status, "approved")
        link.refresh_from_db()
        self.assertFalse(link.is_active)

    def test_dairy_dashboard_pending_payments_matches_balance(self):
        self.auth()
        self.link_farmer()
        collection = create_collection(self.farmer, self.agent, quantity=10.00)
        create_paid_payment(self.farmer, self.agent, total_amount="200.00")

        response = self.client.get("/api/dairy/dashboard/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected_pending = float(collection.amount - Decimal("200.00"))
        self.assertEqual(response.data["pending_payments"], expected_pending)

    def test_dairy_dashboard_ignores_payments_of_other_operators(self):
        self.auth()
        self.link_farmer()
        other_agent = create_user("agent_payer", role="agent", phone="agent_pa")
        collection = create_collection(self.farmer, self.agent, quantity=10.00)
        create_paid_payment(self.farmer, other_agent, total_amount=collection.amount)

        response = self.client.get("/api/dairy/dashboard/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["pending_payments"], float(collection.amount))

    def test_dairy_dashboard_ignores_collections_of_other_operators(self):
        self.auth()
        self.link_farmer()
        other_agent = create_user("agent_other", role="agent", phone="agent_ot")
        create_collection(self.farmer, other_agent, quantity=10.00)

        response = self.client.get("/api/dairy/dashboard/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["pending_payments"], 0.0)

    def test_pending_payment_report_lists_outstanding_farmers(self):
        self.auth()
        self.link_farmer()
        create_collection(self.farmer, self.agent, quantity=10.00)

        response = self.client.get("/api/dairy/reports/?report_type=pending_payment")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["records"]), 1)
        self.assertEqual(response.data["records"][0]["farmer_id"], self.farmer.id)
        self.assertEqual(response.data["records"][0]["pending_balance"], 560.0)

    def test_pending_payment_report_excludes_settled_farmers(self):
        self.auth()
        self.link_farmer()
        collection = create_collection(self.farmer, self.agent, quantity=10.00)
        create_paid_payment(self.farmer, self.agent, total_amount=collection.amount)

        response = self.client.get("/api/dairy/reports/?report_type=pending_payment")
        self.assertEqual(len(response.data["records"]), 0)

    def test_linked_farmers_show_pending_balance(self):
        self.auth()
        self.link_farmer()
        create_collection(self.farmer, self.agent, quantity=10.00)
        create_paid_payment(self.farmer, self.agent, total_amount="200.00")

        response = self.client.get("/api/dairy/linked-farmers/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["pending_balance"], 360.0)

    def test_notify_pending_payment(self):
        self.auth()
        self.link_farmer()
        create_collection(self.farmer, self.agent, quantity=10.00)

        response = self.client.post(
            "/api/dairy/notify-pending-payment/", {"farmer_id": self.farmer.id}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["detail"], "Notification sent successfully.")
        self.assertTrue(
            Notification.objects.filter(recipient=self.farmer, title="Pending Payment Reminder").exists()
        )

    def test_farmer_payable_summary_shows_overpaid_amount(self):
        self.auth()
        self.link_farmer()
        create_collection(self.farmer, self.agent, quantity=10.00)
        create_paid_payment(self.farmer, self.agent, total_amount="600.00")

        response = self.client.get(f"/api/dairy/farmer-payable-summary/{self.farmer.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["pending_balance"], 0.0)
        self.assertEqual(response.data["overpaid_amount"], 40.0)
        self.assertTrue(response.data["is_overpaid"])

    def test_farmer_payable_summary_not_overpaid(self):
        self.auth()
        self.link_farmer()
        create_collection(self.farmer, self.agent, quantity=10.00)
        create_paid_payment(self.farmer, self.agent, total_amount="300.00")

        response = self.client.get(f"/api/dairy/farmer-payable-summary/{self.farmer.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["pending_balance"], 260.0)
        self.assertEqual(response.data["overpaid_amount"], 0.0)
        self.assertFalse(response.data["is_overpaid"])

    def test_linked_farmers_show_overpaid_state(self):
        self.auth()
        self.link_farmer()
        create_collection(self.farmer, self.agent, quantity=10.00)
        create_paid_payment(self.farmer, self.agent, total_amount="600.00")

        response = self.client.get("/api/dairy/linked-farmers/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["pending_balance"], 0.0)
        self.assertEqual(response.data[0]["overpaid_amount"], 40.0)
        self.assertTrue(response.data[0]["is_overpaid"])


class MilkRecordDeletionTests(PaymentTestMixin, APITestCase):
    """Deleting a milk record must not erase an amount that was already paid out."""

    def test_delete_record_that_was_already_paid_is_blocked(self):
        self.auth()
        collection = create_collection(self.farmer, self.agent, quantity=10.00)
        create_paid_payment(self.farmer, self.agent, total_amount=collection.amount)

        response = self.client.delete(f"/api/collection/{collection.id}/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertTrue(MilkCollection.objects.filter(id=collection.id).exists())

    def test_delete_record_when_farmer_overpaid_is_blocked(self):
        self.auth()
        first = create_collection(self.farmer, self.agent, quantity=10.00)
        create_collection(self.farmer, self.agent, quantity=5.00)
        create_paid_payment(self.farmer, self.agent, total_amount="400.00")

        response = self.client.delete(f"/api/collection/{first.id}/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertTrue(MilkCollection.objects.filter(id=first.id).exists())

    def test_delete_unpaid_record_is_allowed(self):
        self.auth()
        collection = create_collection(self.farmer, self.agent, quantity=10.00)

        response = self.client.delete(f"/api/collection/{collection.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        self.assertFalse(MilkCollection.objects.filter(id=collection.id).exists())

    def test_delete_settled_record_is_blocked(self):
        """After a payout the record's amount has been disbursed, so it cannot be removed."""
        self.auth()
        self.link_farmer()
        collection = create_collection(self.farmer, self.agent, quantity=10.00)
        create_paid_payment(self.farmer, self.agent, total_amount=collection.amount)

        response = self.client.delete(f"/api/collection/{collection.id}/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertTrue(MilkCollection.objects.filter(id=collection.id).exists())

    def test_partial_payment_blocks_deleting_covered_record(self):
        self.auth()
        collection = create_collection(self.farmer, self.agent, quantity=10.00)
        create_paid_payment(self.farmer, self.agent, total_amount="560.00", paid_amount="300.00")

        response = self.client.delete(f"/api/collection/{collection.id}/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertTrue(MilkCollection.objects.filter(id=collection.id).exists())
