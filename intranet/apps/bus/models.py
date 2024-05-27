from django.db import models


class Route(models.Model):
    """A bus route (e.g. TJ-24)"""

    ARRIVAL_STATUSES = (("a", "Arrived (In the lot)"), ("d", "Delayed"), ("o", "On Time (Expected)"))

    route_name = models.CharField(max_length=30, unique=True)
    space = models.CharField(max_length=4, blank=True)
    bus_number = models.CharField(max_length=5, blank=True)
    status = models.CharField("arrival status", choices=ARRIVAL_STATUSES, max_length=1, default="o")

    def reset_status(self):
        """Reset status to (on time)"""
        self.status = "o"
        self.space = ""
        self.save(update_fields=["status", "space"])

    def __str__(self):
        return self.route_name

    class Meta:
        ordering = ["route_name"]

from html.parser import HTMLParser

class BusTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.data = []
        self.capture = False

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            self.capture = True

    def handle_endtag(self, tag):
        if tag == "td":
            self.capture = False

    def handle_data(self, data):
        if self.capture and data.startswith("JT-"):
            self.data.append(data.split()[0]) # We only want the bus name

parser = BusTableParser()

class BusAnnouncement(models.Model):
    """Announcement on the bus page. Only one instance of this model is allowed."""

    message = models.TextField(blank=True)

    @classmethod
    def object(cls):
        return cls.objects.first() or cls.objects.create()

    def save(self, *args, **kwargs):
        self.pk = self.id = 1
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Bus announcement: {self.message}"
