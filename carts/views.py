from django.shortcuts import render, redirect, get_object_or_404
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, Http404, JsonResponse
from django.conf import settings

from django.views.generic.base import View
from django.views.generic.detail import SingleObjectMixin, DetailView
from django.views.generic.edit import FormMixin
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages

from .models import Cart, CartItem
from products.models import Variation
from orders.models import UserCheckout, Order, UserAddress
from orders.forms import GuestCheckoutForm
from orders.mixins import CartOrderMixin

import pdb

import braintree
braintree.Configuration.configure(
    braintree.Environment.Sandbox,
    '79ca5f34fbc3b9eb1157211d37731a0e',
    'jnpbmcwvp3v67pk6',
    'f3yp35zj726j2xz4'
)
# 'PRIVATE_ID',
# 'PUBLIC_KEY',
# 'MERCHANT_ID'

if settings.DEBUG:
    braintree.Configuration.configure(braintree.Environment.Sandbox,
                                      merchant_id = settings.BRAINTREE_MERCHANT_ID,
                                      public_key = settings.BRAINTREE_PUBLIC,
                                      private_key = settings.BRAINTREE_PRIVATE)
# Create your views here.


class CartView(SingleObjectMixin, View):
    model = Cart
    template_name = "carts/view.html"

    def get_object(self, *args, **kwargs):
        self.request.session.set_expiry(0)
        cart_id = self.request.session.get("cart_id")
        if cart_id == None:
            cart = Cart()
            cart.save()
            cart_id = cart.id
            self.request.session["cart_id"] = cart.id
        cart = Cart.objects.get(id=cart_id)
        if self.request.user.is_authenticated():
            cart.user = self.request.user
            cart.save()
        print("get_object() cart: ", cart)
        return cart

    def get(self, request, *args, **kwargs):
        cart = self.get_object()
        item_id = request.GET.get("item")
        delete_item = request.GET.get("delete", False)
        item_added = False
        created_item = False
        if item_id:
            item_instance = get_object_or_404(Variation, id=item_id)
            qty = request.GET.get("qty",1)
            try:
                if int(qty) < 1:
                    delete_item = True
            except:
                raise Http404

            #either create an item or retrieve what's already there
            cart_item, created_item = CartItem.objects.get_or_create(
                cart=cart, item=item_instance)
            if created_item:
                item_added = True

            if delete_item:
                cart_item.delete()
            else:
                cart_item.quantity = qty
                cart_item.save()

            if not request.is_ajax():
                return HttpResponseRedirect(reverse("cart"))

        if request.is_ajax():
            print("ajax request: ", request.GET.get("item"))
            try:
                total = cart_item.line_item_total
            except:
                total = None
            try:
                cart_total = cart_item.cart.total
            except:
                cart_total = None
            try:
                tax_total = cart_item.cart.tax_total
            except:
                tax_total = None

            try:
                subtotal = cart_item.cart_subtotal
            except:
                subtotal = None
            try:
                total_items = cart_item.cart.items.count()
            except:
                total_items = 0
            data = {
                "deleted": delete_item,
                "item_added": created_item,
                "line_total": total,
                "subtotal": subtotal,
                "cart_total": cart_total,
                "tax_total": tax_total,
                "total_items": total_items,
            }
            print("ajax data: ", data )
            return JsonResponse(data)

        context = {
            "object":self.get_object()
        }
        print("stuff", context["object"])

        template = self.template_name
        return render(request, template, context)

class CheckoutView(CartOrderMixin, FormMixin, DetailView):
    model = Cart
    template_name = "carts/checkout_view.html"
    form_class = GuestCheckoutForm


    def get_object(self, *args, **kwargs):
        cart = self.get_cart()
        if cart == None:
            return None
        return cart

    def get_context_data(self, *args, **kwargs):
        context = super(CheckoutView, self).get_context_data( *args, **kwargs)
        user_can_continue = False
        user_check_id = self.request.session.get("user_checkout_id")
        print("THis is the session ---", self.request.session.session_key)
        # print("user_check_id: ", user_check_id)
        # # print("self.request.session.get('user_checkout_id'): ",
        # #     self.request.session.get("user_checkout_id"))
        if not self.request.user.is_authenticated() or user_check_id is None:
            context["login_form"] = AuthenticationForm()
            context["next_url"] = self.request.build_absolute_uri()
        elif self.request.user.is_authenticated() or user_check_id is not None:
            user_can_continue = True
        else:
            pass

        if self.request.user.is_authenticated():
            user_checkout, created = UserCheckout.objects.get_or_create(
                email=self.request.user.email)
            user_checkout.user = self.request.user
            user_checkout.save()
            context["client_token"] = user_checkout.get_client_token()
            # print("request session", self.request.session)
            self.request.session["user_checkout_id"] = user_checkout.id
            # print("request session", self.request.session)
        elif not self.request.user.is_authenticated() and user_check_id is None:
            context["login_form"] = AuthenticationForm()
            context["next_url"] = self.request.build_absolute_uri()
        else:
            pass

        if user_check_id != None:
            user_can_continue = True
            #GUEST USER - Making sure an authenticated token and a guest user
            #token don't come at the same time
            if not self.request.user.is_authenticated():
                user_checkout_2 = UserCheckout.objects.get(id=user_check_id)
                context["client_token"] = user_checkout_2.get_client_token()
                pdb.set_trace()
        context["order"] = self.get_order()
        context["form"] = self.get_form()
        context["user_can_continue"] = user_can_continue
        print(context, "---User Checkout ID ---", user_check_id)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()

        if form.is_valid():
            email = form.cleaned_data.get("email")
            user_checkout, created = UserCheckout.objects.get_or_create(email=email)
            request.session["user_checkout_id"] = user_checkout.id
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse("checkout")

    def get(self, request, *args, **kwargs):
        print(request.GET)
        # pdb.set_trace()
        get_data = super(CheckoutView, self).get(request, *args, **kwargs)
        cart = self.get_object()
        if cart is None:
            return redirect("cart")
        new_order = self.get_order()
        print('get(): request.session.get("user_checkout_id"): ', request.session.get("user_checkout_id"))
        user_checkout_id = request.session.get("user_checkout_id")
        if user_checkout_id is not None:
            user_checkout = UserCheckout.objects.get(id = user_checkout_id)
            print("CheckoutView, get(), user_checkout", user_checkout)
            if new_order.billing_address is None or new_order.shipping_address is None:
                return redirect("address_form")
            new_order.user = user_checkout #user_checkout_id
            new_order.save()
        return get_data

class CheckoutFinalView(CartOrderMixin, View):
    def get(self, request, *args, **kwargs):
        return redirect("checkout")

    def post(self, request, *args, **kwargs):
        # print("CheckoutFinalView POST:", request.POST)
        order = self.get_order()
        nonce = request.POST.get("payment_method_nonce")
        if nonce:
            result = braintree.Transaction.sale({
                "payment_method_nonce" : nonce,
                "amount" : order_total,
                "billing" : {
                    "postal_code" : "{}".format(order.billing_address.zipcode),
                },
                "options" : {
                    "submit_for_settlement" : True,
                },
            })
            if result.is_success:
                print("transaction id:", result.transaction.id)
                order.mark_completed(order_id=result.transaction.id)
                messages.success(request, "Thank you for your order!")
                print("session ids:", request.session["cart_id"], request.session["order_id"])
                del request.session["cart_id"]
                del request.session["order_id"]
                print("session ids:", request.session["cart_id"], request.session["order_id"])
            else:
                messages.success(request, "{}".format(result.message))
                return redirect("checkout")
        return redirect("order_detail", pk=order.pk)
