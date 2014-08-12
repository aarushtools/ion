# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from itertools import chain
import logging
import datetime
from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError, NON_FIELD_ERRORS
from ..users.models import User
from . import exceptions as eighth_exceptions

logger = logging.getLogger(__name__)


class EighthSponsor(models.Model):
    """Represents a sponsor for an eighth period activity.

    A sponsor could be an actual user or just a name.

    Attributes:
        - user -- A :class:`User<intranet.apps.users.models.User>`\
                  object for the sponsor.
        - name -- The name of the sponsor

    """
    first_name = models.CharField(max_length=63)
    last_name = models.CharField(max_length=63)
    user = models.ForeignKey(User, null=True, blank=True)
    online_attendance = models.BooleanField(default=True)

    class Meta:
        unique_together = (("first_name", "last_name", "user", "online_attendance"),)

    def __unicode__(self):
        try:
            l = self.last_name
        except NameError:
            l = ""
        try:
            f = self.first_name
        except NameError:
            f = ""
        return "{}, {}".format(l, f)


class EighthRoom(models.Model):
    """Represents a room in which an eighth period activity can be held

    Attributes:
        - Attribute -- Description.

    """
    name = models.CharField(max_length=63)
    capacity = models.SmallIntegerField(default=-1)

    unique_together = (("name", "capacity"),)

    def __unicode__(self):
        return "{} ({})".format(self.name, self.capacity)


class EighthActivityExcludeDeletedManager(models.Manager):
    def get_query_set(self):
        return super(EighthActivityExcludeDeletedManager, self).get_query_set().exclude(deleted=True)


class EighthActivity(models.Model):
    """Represents an eighth period activity.

    Attributes:
        - name -- The name of the activity.
        - sponsors -- The :class:`EighthSponsor`s for the activity.

    """
    objects = models.Manager()
    undeleted_objects = EighthActivityExcludeDeletedManager()

    name = models.CharField(max_length=63, unique=True)
    description = models.CharField(max_length=255, blank=True)
    sponsors = models.ManyToManyField(EighthSponsor, blank=True)
    rooms = models.ManyToManyField(EighthRoom, blank=True)

    restricted = models.BooleanField(default=False)
    presign = models.BooleanField(default=False)
    one_a_day = models.BooleanField(default=False)
    both_blocks = models.BooleanField(default=False)
    sticky = models.BooleanField(default=False)
    special = models.BooleanField(default=False)

    # users_allowed = models.ManyToManyField(User, blank=True)

    deleted = models.BooleanField(blank=True, default=False)

    @property
    def capacity(self):
        all_rooms = self.rooms.all()
        if len(all_rooms) == 0:
            capacity = -1
        else:
            capacity = 0
            for room in all_rooms:
                capacity += room.capacity
        return capacity

    class Meta:
        verbose_name_plural = "eighth activities"

    def __unicode__(self):
        return self.name + (" (Deleted)" if self.deleted else "")


class EighthBlockManager(models.Manager):
    def get_first_upcoming_block(self):
        """Gets the first upcoming block (the first block that will
        take place in the future). If there is no block in the future,
        the most recent block will be returned

        Returns: the `EighthBlock` object

        """

        now = datetime.datetime.now()

        # Show same day if it's before 17:00
        if now.hour < 17:
            now = now.replace(hour=0, minute=0, second=0, microsecond=0)

        try:
            block = self.order_by("date", "block_letter") \
                        .filter(date__gte=now)[0]
        except IndexError:
            block = None
        return block

    def get_current_blocks(self):
        try:
            first_upcoming_block = self.get_first_upcoming_block()
            if first_upcoming_block is None:
                raise EighthBlock.DoesNotExist()
            block = self.prefetch_related("eighthscheduledactivity_set") \
                        .get(id=first_upcoming_block.id)
        except EighthBlock.DoesNotExist:
            return []

        return block.get_surrounding_blocks()


class EighthBlock(models.Model):
    """Represents an eighth period block.

    Attributes:
        - date -- The date of the block.
        - block_letter -- The block letter (e.g. A, B).
        - locked -- Whether signups are closed.
        - activities -- List of \
                        :class:`EighthScheduledActivity`s for the block.

    """

    objects = EighthBlockManager()

    date = models.DateField(null=False)
    block_letter = models.CharField(max_length=1)
    locked = models.BooleanField(default=False)
    activities = models.ManyToManyField(EighthActivity,
                                        through="EighthScheduledActivity",
                                        blank=True)

    def save(self, *args, **kwargs):
            letter = getattr(self, "block_letter", None)
            if letter:
                self.block_letter = letter.capitalize()

            super(EighthBlock, self).save(*args, **kwargs)

    def next_blocks(self, quantity=-1):
        blocks = EighthBlock.objects \
                            .order_by("date", "block_letter") \
                            .filter(Q(date__gt=self.date)
                                    | (Q(date=self.date)
                                    & Q(block_letter__gt=self.block_letter)))
        if quantity == -1:
            return blocks
        return blocks[:quantity + 1]

    def previous_blocks(self, quantity=-1):
        blocks = EighthBlock.objects \
                            .order_by("-date", "-block_letter") \
                            .filter(Q(date__lt=self.date)
                                    | (Q(date=self.date)
                                    & Q(block_letter__lt=self.block_letter)))
        if quantity == -1:
            return reversed(blocks)
        return reversed(blocks[:quantity + 1])

    def get_surrounding_blocks(self):
        """Get the blocks around the one given.
           Returns: a list of all of those blocks."""

        next = self.next_blocks()
        prev = self.previous_blocks()

        surrounding_blocks = list(chain(prev, [self], next))
        return surrounding_blocks

    def __unicode__(self):
        return "{}: {}".format(str(self.date), self.block_letter)

    class Meta:
        unique_together = (("date", "block_letter"),)


class EighthScheduledActivity(models.Model):
    """Represents the relationship between an activity and a block in
    which it has been scheduled.

    Attributes:
        - block -- the :class:`EighthBlock` during which an \
                   :class:`EighthActivity` has been scheduled
        - activity -- the scheduled :class:`EighthActivity`
        - members -- the :class:`User<intranet.apps.users.models.User>`s\
                     who have signed up for an :class:`EighthBlock`
        - comments -- notes for the Eighth Office
        - sponsors -- :class:`EighthSponsor`s that will override the \
                      :class:`EighthActivity`'s default sponsors
        - rooms -- :class:`EighthRoom`s that will override the \
                   :class:`EighthActivity`'s default rooms
        - attendance_taken -- whether the :class:`EighthSponsor` for \
                              the scheduled :class:`EighthActivity` \
                              has taken attendance yet
        - cancelled -- whether the :class:`EighthScheduledActivity` \
                       has been cancelled

    """
    block = models.ForeignKey(EighthBlock)
    activity = models.ForeignKey(EighthActivity)
    members = models.ManyToManyField(User, through="EighthSignup")

    comments = models.CharField(max_length=255, blank=True)

    # Overridden attributes
    sponsors = models.ManyToManyField(EighthSponsor, blank=True)
    rooms = models.ManyToManyField(EighthRoom, blank=True)
    capacity = models.SmallIntegerField(null=True, blank=True)

    attendance_taken = models.BooleanField(default=False)
    cancelled = models.BooleanField(default=False)

    def get_true_sponsors(self):
        """Get the sponsors for the scheduled activity, taking into account
        activity defaults and overrides.
        """

        sponsors = self.sponsors.all()
        if len(sponsors) > 0:
            return sponsors
        else:
            return self.activity.sponsors.all()

    def get_true_rooms(self):
        """Get the rooms for the scheduled activity, taking into account
        activity defaults and overrides.
        """

        rooms = self.rooms.all()
        if len(rooms) > 0:
            return rooms
        else:
            return self.activity.rooms.all()

    def get_true_capacity(self):
        """Get the capacity for the scheduled activity, taking into
        account activity defaults and overrides.
        """

        if self.capacity is not None:
            return self.capacity
        else:
            return self.activity.capacity

    def is_full(self):
        capacity = self.get_true_capacity()
        if capacity != -1:
            num_signed_up = self.eighthsignup_set.count()
            return num_signed_up >= capacity
        return False

    def is_too_early_to_signup(self, now=None):
        if now is None:
            now = datetime.datetime.now()

        activity_date = datetime.datetime \
                                .combine(self.block.date,
                                         datetime.time(0, 0, 0))
        presign_period = datetime.timedelta(days=2)

        return (now < (activity_date - presign_period))

    def add_user(self, user, request=None, force=False):
        """Sign up a user to this scheduled activity if possible.

        Raises an exception if there's a problem signing the user up
        unless the signup is forced.

        """

        if request is not None:
            force = force or (("force" in request.GET) and
                              request.user.is_eighth_admin)

        if not force:
            # Check if the user who sent the request has the permissions to
            # change the target user's signups
            if request is not None:
                if user != request.user and not request.user.is_eighth_admin:
                    raise eighth_exceptions.SignupForbidden()

             # Check if the block has been locked
            if self.block.locked:
                raise eighth_exceptions.BlockLocked()

            # Check if the scheduled activity has been cancelled
            if self.cancelled:
                raise eighth_exceptions.ScheduledActivityCancelled()

            # Check if the activity has been deleted
            if self.activity.deleted:
                raise eighth_exceptions.ActivityDeleted()

            # Check if the activity is full
            if self.is_full():
                raise eighth_exceptions.ActivityFull()

            # Check if it's too early to sign up for the activity
            if self.activity.presign:
                if self.is_too_early_to_signup():
                    raise eighth_exceptions.Presign()

            # Check if the user is already stickied into an activity
            in_a_stickie = self.eighthsignup_set \
                               .filter(user=user,
                                       scheduled_activity__activity__sticky=True) \
                               .count() != 0
            if in_a_stickie:
                raise eighth_exceptions.Sticky()

            # Check if signup would violate one-a-day constraint
            if self.activity.one_a_day:
                in_act = self.eighthsignup_set \
                             .exclude(scheduled_activity__block=self.block) \
                             .filter(user=user,
                                     scheduled_activity__block__date=self.block.date,
                                     scheduled_activity__activity=self.activity) \
                             .count() != 0
                if in_act:
                    raise eighth_exceptions.OneADay()

            # Check if user is allowed in the activity if restricted
            # if self.activity.restricted:
            #     allowed = self.activity.users_allowed


        # Everything's good to go - complete the signup
        try:
            existing_signup = EighthSignup.objects \
                                          .get(user=user,
                                               scheduled_activity__block=self.block)
            existing_signup.scheduled_activity = self
            existing_signup.save()
        except EighthSignup.DoesNotExist:
            pass
            EighthSignup.objects.create(user=user,
                                        scheduled_activity=self)

    class Meta:
        unique_together = (("block", "activity"),)
        verbose_name_plural = "eighth scheduled activities"

    def __unicode__(self):
        cancelled_str = " (Cancelled)" if self.cancelled else ""
        return "{} on {}{}".format(self.activity, self.block, cancelled_str)


class EighthSignup(models.Model):
    """Represents a signup/membership in an eighth period activity.

    Attributes:
        - user -- The :class:`User<intranet.apps.users.models.User>`\
                  who has signed up.
        - scheduled_activity -- The :class:`EighthScheduledActivity` for which
                                the user \
                                has signed up.
        - after_deadline -- Whether the signup was after deadline.

    """
    user = models.ForeignKey(User, null=False)
    scheduled_activity = models.ForeignKey(EighthScheduledActivity, null=False, db_index=True)
    after_deadline = models.BooleanField(default=False)

    def validate_unique(self, *args, **kwargs):
        super(EighthSignup, self).validate_unique(*args, **kwargs)

        if self.__class__.objects.exclude(pk=self.pk).filter(user=self.user, scheduled_activity__block=self.scheduled_activity.block):
            raise ValidationError({
                NON_FIELD_ERRORS: ("EighthSignup already exists for the User "
                                   "and the EighthScheduledActivity's block",)
            })

    def __unicode__(self):
        return "{}: {}".format(self.user,
                               self.scheduled_activity)

    class Meta:
        unique_together = (("user", "scheduled_activity"),)


class EighthAbsence(models.Model):
    """Represents a user's absence for an eighth period block.

    Attributes:
        - block -- The `EighthBlock` of the absence.
        - user -- The :class:`User<intranet.apps.users.models.User>`\
                  who was absent.

    """
    block = models.ForeignKey(EighthBlock)
    user = models.ForeignKey(User)

    def __unicode__(self):
        return "{}: {}".format(self.user, self.block)

    class Meta:
        unique_together = (("block", "user"),)
