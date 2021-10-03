from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import F, Q
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from django.views.generic import DetailView, ListView, View
from django.conf import settings
from django.core.paginator import Paginator

from .models import Category, Subcategory, Item, Order, Step, OrderStep, OrderItem

from loguru import logger
import json
import operator


class CategoryView(ListView):
    model = Category
    template_name = 'shop/category.html'
    paginate_by = 10
    ordering = ('title',)


class SubcategoryView(ListView):
    model = Subcategory
    template_name = 'shop/subcategory.html'
    context_object_name = 'subcategories'
    paginate_by = 20
    ordering = ('title',)

    def get_queryset(self):
        subcategories = Subcategory.objects.filter(
            category__slug=self.kwargs.get('slug')
        ).order_by('title')
        return subcategories


class ProductsView(ListView):
    model = Item
    template_name = 'shop/items.html'
    context_object_name = 'items'
    paginate_by = 20
    ordering = ('price', 'title',)

    def get_queryset(self):
        if len(self.kwargs) == 1:
            items = Item.objects.filter(
                subcategory__slug=self.kwargs.get('slug'),
            ).order_by('price', 'title')
            return items
        return Item.objects.all()


class CheckoutView(LoginRequiredMixin, View):
    model = Order

    def get(self, *args, **kwargs):
        try:
            order = Order.objects.prefetch_related('order_items').get(
                user=self.request.user, ordered=False, shipped=False
            )
            context = {'object': order}
            return render(self.request, "shop/checkout.html", context)
        except Exception as e:
            logger.info(str(e))
            messages.error(self.request, _("You do not have an active order"))
            return redirect('shop:category')


class ProductView(DetailView):
    model = Item
    template_name = 'shop/item.html'
    context_object_name = 'item'

    def get_queryset(self):
        return Item.objects.filter(slug=self.kwargs.get('slug'))


class CartView(LoginRequiredMixin, View):
    def get(self, *args, **kwargs):
        try:
            logger.info(self.request.user)
            order = Order.objects.get(
                user=self.request.user,
                ordered=False,
                shipped=False
            )
            if len(order.order_steps.all()) <= 0:
                pay_step = Step.objects.get(name_step='оплата')
                package_step = Step.objects.get(name_step='упаковка')
                transport_step = Step.objects.get(name_step='доставка в город')
                delivery_step = Step.objects.get(
                    name_step='доставка по городу')

                order_step1 = OrderStep.objects.create(
                    order=order, step=pay_step)
                order_step2 = OrderStep.objects.create(
                    order=order, step=package_step)
                order_step3 = OrderStep.objects.create(
                    order=order, step=transport_step)
                order_step4 = OrderStep.objects.create(
                    order=order, step=delivery_step)
                order.order_steps.add(
                    order_step1, order_step2, order_step3, order_step4
                )

            context = {'object': order}
            return render(self.request, 'shop/cart.html', context)
        except ObjectDoesNotExist:
            messages.error(self.request, "You do not have an active order")
            return redirect('/')


def search_view(request):
    if request.method == 'POST':
        search_query = request.POST.get('search')
        items = Item.objects.filter(title__icontains=search_query)
        return render(request, 'shop/search.html', {'items': items})
    return redirect(request.path_info)


@logger.catch
@login_required
def ajax_add_to_cart(request):
    event_json = json.loads(request.body)
    try:
        item = Item.objects.get(slug=event_json.get('slug'))
    except:
        return JsonResponse({'error': _("This item doesn't exist")}, status=400)

    try:
        order, order_created = Order.objects.get_or_create(
            user=request.user, ordered=False, shipped=False
        )
        order_item, order_item_created = OrderItem.objects.get_or_create(
            order=order, item=item
        )

        return JsonResponse({}, status=201)
    except Exception as e:
        logger.error(str(e))
        return JsonResponse({}, status=405)


@logger.catch
@login_required
def ajax_remove_from_cart(request):
    event_json = json.loads(request.body)
    slug = event_json.get('slug')
    try:
        item = Item.objects.get(slug=slug)
    except Item.objects.DoesNotExist:
        return JsonResponse({'error': _("This item doesn't exist")}, status=400)

    try:
        order = Order.objects.get(
            user=request.user, ordered=False, shipped=False
        )
    except Order.DoesNotExist:
        return JsonResponse({'error': 'You do not have an active order'}, status=400)

    try:
        order_item = OrderItem.objects.get(
            order=order, item=item
        )
    except OrderItem.DoesNotExist:
        return JsonResponse({'error': 'No such item in your cart'}, status=400)

    order_item.delete()
    return JsonResponse({}, status=202)


@logger.catch
@login_required
def ajax_edit_cart(request):
    posted_data = json.loads(request.body)
    slug = posted_data.get('slug')
    quantity = posted_data.get('quantity')
    try:
        item = Item.objects.get(slug=slug)
    except Item.DoesNotExist:
        return JsonResponse({'error': 'This item does not exist'}, status=400)

    try:
        order = Order.objects.get(
            user=request.user,
            ordered=False,
            shipped=False
        )
    except Order.DoesNotExist:
        return JsonResponse({'error': 'You do not have an active order'}, status=400)

    try:
        order_item = OrderItem.objects.get(
            item=item,
            order=order
        )
    except OrderItem.DoesNotExist:
        return JsonResponse({'error': 'No such item in your cart'}, status=400)

    order_item.quantity = quantity
    order_item.save()
    return JsonResponse({}, status=200)
