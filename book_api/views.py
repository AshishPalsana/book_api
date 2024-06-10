from django.shortcuts import render, redirect
from .models import Book, Rental
from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from datetime import datetime, date
from django.contrib import messages
from django.contrib.auth.decorators import (
    login_required,
)
from django.views.decorators.csrf import csrf_exempt
import requests
import razorpay


def index(request):
    bookdata = Book.objects.all()
    return render(request, "index.html", {"bookdata": bookdata})


def register_view(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            login(request, form.save())
            return redirect("login")
    else:
        form = UserCreationForm()
    return render(request, "register.html", {"form": form})


def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect("/")
    else:
        form = AuthenticationForm()
    return render(request, "login.html", {"form": form})


def signout(request):
    logout(request)
    return redirect("index")


def details(request, id):
    bookdata = Book.objects.get(id=id)
    print("book:", bookdata)
    return render(request, "details.html", {"book": bookdata})


@login_required
def add_to_cart(request, book_id_id):
    book = Book.objects.get(id=book_id_id)
    return_date = datetime.strptime(request.POST["return_date"], "%Y-%m-%d").date()
    print("return_date", return_date)
    rental, created = Rental.objects.get_or_create(
        user=request.user, book_id_id=book_id_id, return_date=return_date
    )
    rental_period = (return_date - date.today()).days

    if rental_period > 30:
        extra_months = (rental_period - 30) // 30
        rental.fees = int(extra_months * (book.page / 100))
    else:
        rental.fees = 0
    rental.save()
    return redirect("view_cart")


@login_required
def view_cart(request):
    cart_items = Rental.objects.filter(user=request.user)
    total_price_usd = sum(item.fees for item in cart_items)

    exchange_rate = 75
    total_price_inr = total_price_usd * exchange_rate
    total_price_paise = int(total_price_inr * 100)

    if total_price_inr < 100:
        return render(
            request,
            "cart.html",
            {
                "cart_items": cart_items,
                "total_price": total_price_inr,
                "show_payment": False,
            },
        )

    client = razorpay.Client(
        auth=("rzp_test_V9lMRSNuZ8bCJX", "47EvThmxXTtBwR4QBLfrwZTe")
    )
    payment = client.order.create(dict(amount=total_price_paise, currency="INR"))

    return render(
        request,
        "cart.html",
        {
            "cart_items": cart_items,
            "total_price": total_price_inr,
            "payment": payment,
            "show_payment": True,
        },
    )


def remove_from_cart(request, item_id):
    cart_item = Rental.objects.get(id=item_id)
    cart_item.delete()
    return redirect("view_cart")


def latestbook(request):
    bookdata = Book.objects.order_by("-id")[:5]  # top 5 Book
    return render(request, "latestbook.html", {"bookdata": bookdata})


def add_book(request):
    if request.method == "POST":
        title = request.POST.get("title")
        if title:
            response = requests.get(
                f"https://openlibrary.org/search.json?title={title}"
            )
            data = response.json()
            if data["docs"]:
                book_data = data["docs"][0]
                publish_date_str = book_data.get("publish_date", [""])[0]
                try:
                    publish_date = datetime.strptime(publish_date_str, "%Y").date()
                except ValueError:
                    publish_date = None
                book, created = Book.objects.get_or_create(
                    title=book_data["title_suggest"],
                    publish_date=publish_date,
                    page=book_data.get("number_of_pages_median")
                    or book_data.get("number_of_pages", 0),
                    author_name=book_data.get("author_name", [""])[0],
                )
            else:
                messages.error(request, "Book not found.")
        else:
            messages.error(request, "Title is required.")
    return render(request, "addbook.html")


@csrf_exempt
def payment_success(request):
    if request.method == "POST":
        payment_id = request.POST.get("razorpay_payment_id")
        order_id = request.POST.get("razorpay_order_id")
        signature = request.POST.get("razorpay_signature")

        client = razorpay.Client(
            auth=("rzp_test_V9lMRSNuZ8bCJX", "47EvThmxXTtBwR4QBLfrwZTe")
        )
        params_dict = {
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        }

        try:
            client.utility.verify_payment_signature(params_dict)
            Rental.objects.filter(user=request.user).delete()
            return redirect("payment_success")
        except:
            messages.error(request, "Payment verification failed. Please try again.")
            return redirect("view_cart")

    return render(request, "payment_success.html")
