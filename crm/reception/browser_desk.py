"""Optional Playwright smoke test. Run with manage.py test reception.browser_desk."""
import os
from datetime import timedelta
from secrets import token_urlsafe

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import LiveServerTestCase, override_settings
from django.utils import timezone
from playwright.sync_api import expect, sync_playwright

from .access import RECEPTION_GROUP, setup_demo_roles
from .models import Apartment, WalkBooking, WalkSession
from .services import _change_status, _create_request


@override_settings(STATIC_URL="/static/", MEDIA_URL="/media/")
class DeskBrowserTests(LiveServerTestCase):
    def test_guest_request_staff_confirmation_and_cancellation(self):
        call_command("seed_demo", shift=True, verbosity=0)
        setup_demo_roles()
        password = token_urlsafe()
        user = get_user_model().objects.create_user("browser-staff", password=password)
        user.groups.add(Group.objects.get(name=RECEPTION_GROUP))
        today = timezone.localdate()
        next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=8)
        walk_day = next_month + timedelta(days=(5 - next_month.weekday()) % 7)
        walk = WalkSession.objects.get(day=walk_day)
        unit = Apartment.objects.get(code="A-103")
        filler = _create_request(unit.pk, walk_day - timedelta(days=1), walk_day + timedelta(days=1), 6)
        _change_status(filler.pk, "confirmed")
        WalkBooking.objects.create(session=walk, stay=filler, adults=6, children=0)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("KINSHORE_BROWSER"))
            for width in (390, 1440):
                with self.subTest(width=width):
                    self.play_shift(browser, width, user.username, password, walk_day)
            browser.close()

    def play_shift(self, browser, width, username, password, walk_day):
        guest = browser.new_page(viewport={"width": width, "height": 840})
        staff = browser.new_page(viewport={"width": width, "height": 840})
        try:
            self.verify_route(guest, staff, username, password, walk_day)
        finally:
            guest.context.close()
            staff.context.close()

    def verify_route(self, guest, staff, username, password, walk_day):
        guest.goto(self.live_server_url + "/site/miniapp.html?room=one")
        guest.get_by_label("Guests").select_option("4")
        today = timezone.localdate()
        arrival = walk_day - timedelta(days=1)
        departure = walk_day + timedelta(days=1)
        guest.locator("#open-calendar").click()
        guest.get_by_role("button", name="Next month").click()
        for day in (arrival, departure):
            guest.locator(f'[data-date="{day.isoformat()}"]').press("Enter")
        offer = guest.locator(".mini-card").filter(has_text="Poolside One Bedroom")
        expect(offer).to_contain_text("€270 for 2 nights")
        offer.get_by_role("button", name="Review request").click()
        guest.get_by_role("dialog", name="Before you send").get_by_role("button", name="Send demo request").click()
        receipt = guest.locator("#stay-list article")
        expect(receipt).to_contain_text("Awaiting confirmation")
        reference = receipt.get_by_text("Reference", exact=False).inner_text().split()[-1]

        staff.goto(self.live_server_url + "/reception/")
        staff.get_by_label("Username").fill(username)
        staff.get_by_label("Password").fill(password)
        staff.get_by_role("button", name="Sign in").click()
        expect(staff.get_by_role("heading", name="Today at reception")).to_be_visible()
        day = today.strftime("%Y%m%d")
        expect(staff.get_by_role("region", name="Arrivals")).to_contain_text(f"arrival-{day}")
        expect(staff.get_by_role("region", name="Departures")).to_contain_text(f"departure-{day}")
        staff.get_by_label("Request reference").fill(reference)
        staff.get_by_role("button", name="Search").click()
        staff.get_by_role("link", name=reference).click()
        staff.get_by_role("button", name="Confirm").click()
        expect(staff.get_by_text("Requested → Confirmed", exact=False)).to_contain_text(username)
        guest.get_by_role("button", name="Refresh my requests").click()
        expect(receipt.get_by_text("Confirmed", exact=True)).to_be_visible()
        expect(receipt).to_contain_text("Walk through the arrival gate")
        expect(receipt.get_by_role("link", name="covered parking")).to_have_count(0)
        building_link = receipt.get_by_role("link", name="Find Building")
        building_pin = building_link.get_attribute("href").split("#")[1]
        building_link.click()
        expect(guest.locator(f"#{building_pin}")).to_have_attribute("aria-pressed", "true")
        guest.go_back(wait_until="domcontentloaded")
        walk = receipt.get_by_role("region", name="Pine & Shore Walk")
        expect(walk).to_contain_text("2 of 8 places available")
        walk.get_by_label("Ages 6–15").fill("1")
        walk.get_by_role("button", name="Book the walk").click()
        expect(walk).to_contain_text("Booked · 2 places")
        expect(walk.get_by_role("link", name="Pine terrace")).to_have_attribute("href", "./index.html#pine-terrace")

        staff.get_by_role("link", name="Walks").click()
        staff.get_by_label("Session date").fill(walk_day.isoformat())
        staff.get_by_role("button", name="Show session").click()
        expect(staff.get_by_text("8 of 8 places reserved")).to_be_visible()
        expect(staff.get_by_role("link", name=reference)).to_be_visible()
        self.assertTrue(staff.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        walk.get_by_role("button", name="Cancel walk booking").click()
        expect(walk).to_contain_text("2 of 8 places available")
        staff.reload()
        expect(staff.get_by_text("6 of 8 places reserved")).to_be_visible()

        staff.get_by_role("link", name="Occupancy").click()
        staff.get_by_label("Week starting").fill(arrival.isoformat())
        staff.get_by_role("button", name="Show week").click()
        stays = staff.get_by_role("link", name=reference)
        expect(stays).to_have_count(2)
        self.assertTrue(staff.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        stays.first.click()
        staff.get_by_role("button", name="Cancel request").click()
        guest.get_by_role("button", name="Refresh my requests").click()
        expect(receipt.get_by_text("Cancelled", exact=True)).to_be_visible()
