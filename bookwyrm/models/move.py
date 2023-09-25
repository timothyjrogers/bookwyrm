""" move an object including migrating a user account """
from django.core.exceptions import PermissionDenied
from django.db import models

from bookwyrm import activitypub
from .activitypub_mixin import ActivityMixin
from .base_model import BookWyrmModel
from . import fields
from .status import Status
from bookwyrm.models import User


class Move(ActivityMixin, BookWyrmModel):
    """migrating an activitypub user account"""

    user = fields.ForeignKey(
        "User", on_delete=models.PROTECT, activitypub_field="actor"
    )

    object = fields.CharField(
        max_length=255,
        blank=False,
        null=False,
        activitypub_field="object",
    )

    origin = fields.CharField(
        max_length=255,
        blank=True,
        null=True,
        default="",
        activitypub_field="origin",
    )

    activity_serializer = activitypub.Move

    # pylint: disable=unused-argument
    @classmethod
    def ignore_activity(cls, activity, allow_external_connections=True):
        """don't bother with incoming moves of unknown objects"""
        # TODO
        pass


class MoveUser(Move):
    """migrating an activitypub user account"""

    target = fields.ForeignKey(
        "User",
        on_delete=models.PROTECT,
        related_name="move_target",
        activitypub_field="target",
    )

    def save(self, *args, **kwargs):
        """update user info and broadcast it"""

        # only allow if the source is listed in the target's alsoKnownAs
        if self.user in self.target.also_known_as.all():

            self.user.also_known_as.add(self.target.id)
            self.user.update_active_date()
            self.user.moved_to = self.target.remote_id
            self.user.save(update_fields=["moved_to"])

            if self.user.local:
                kwargs[
                    "broadcast"
                ] = True  # Only broadcast if we are initiating the Move

            super().save(*args, **kwargs)

            for follower in self.user.followers.all():
                if follower.local:
                    MoveUserNotification.objects.create(user=follower, target=self.user)

        else:
            raise PermissionDenied()


class MoveUserNotification(models.Model):
    """notify followers that the user has moved"""

    created_date = models.DateTimeField(auto_now_add=True)

    user = models.ForeignKey(
        "User", on_delete=models.PROTECT, related_name="moved_user_notifications"
    )  # user we are notifying

    target = models.ForeignKey(
        "User", on_delete=models.PROTECT, related_name="moved_user_notification_target"
    )  # new account of user who moved

    def save(self, *args, **kwargs):
        """send notification"""
        super().save(*args, **kwargs)
