from django.contrib.auth.models import Group, Permission
from models import User,OrgAccount, Cluster, Membership
from users.legacy.models import OrgAccount as LegacyOrgAccount, User as LegacyUser, Membership as LegacyMembership
from django.db import transaction
from allauth.account.models import EmailAddress, EmailConfirmation, EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialToken, SocialApp



@transaction.atomic
def migrate_users():
    legacy_users = LegacyUser.objects.using('legacy_v3_db').all()
    new_users = []
    for legacy_user in legacy_users:
        new_user = User(
            username=legacy_user.username,
            first_name=legacy_user.first_name,
            last_name=legacy_user.last_name,
            email=legacy_user.email,
            password=legacy_user.password,  # assuming password hashing is consistent
            is_staff=legacy_user.is_staff,
            is_active=legacy_user.is_active,
            is_superuser=legacy_user.is_superuser,
            last_login=legacy_user.last_login,
            date_joined=legacy_user.date_joined
        )
        new_users.append()
    User.objects.bulk_create(new_users)

@transaction.atomic
def migrate_orgaccounts():
    legacy_orgaccounts = LegacyOrgAccount.objects.using('legacy_v3_db').all()

    for legacy_org in legacy_orgaccounts:
        try:
            # Match the owner by username
            new_owner = User.objects.get(username=legacy_org.owner.username)
        except User.DoesNotExist:
            print(f"Owner {legacy_org.owner.username} does not exist in new database.")
            continue

        new_orgaccount = OrgAccount(
            id=legacy_org.id,
            owner=new_owner,
            name=legacy_org.name,
            point_of_contact_name=legacy_org.point_of_contact_name,
            email=legacy_org.email,
            mfa_code=legacy_org.mfa_code,
        )
        new_orgaccount.save()

@transaction.atomic
def migrate_memberships():
    legacy_memberships = LegacyMembership.objects.using('legacy_v3_db').all()

    for legacy_membership in legacy_memberships:
        # Assuming that the User and OrgAccount models have been migrated already
        try:
            new_user = User.objects.get(username=legacy_membership.user.username)
        except User.DoesNotExist:
            print(f"User {legacy_membership.user.username} does not exist in new database.")
            continue

        try:
            new_org = OrgAccount.objects.get(id=legacy_membership.org.id)
        except OrgAccount.DoesNotExist:
            print(f"OrgAccount with id {legacy_membership.org.id} does not exist in new database.")
            continue

        new_membership = Membership(
            id=legacy_membership.id,
            user=new_user,
            org=new_org,
            active=legacy_membership.active,
            creation_date=legacy_membership.creation_date,
            modified_date=legacy_membership.modified_date,
            delete_requested=legacy_membership.delete_requested,
            activation_date=legacy_membership.activation_date,
        )
        new_membership.save()

@transaction.atomic
def migrate_group():
    # Migrate Group
    legacy_group = Group.objects.using('legacy_v3_db').get(name="PS_Developer")
    new_group = Group(name=legacy_group.name)
    new_group.save()

    # Migrate Group Permissions
    for legacy_permission in legacy_group.permissions.all():
        try:
            # Match permissions by codename as it should be unique and consistent
            permission = Permission.objects.get(codename=legacy_permission.codename)
            new_group.permissions.add(permission)
        except Permission.DoesNotExist:
            print(f"Permission {legacy_permission.codename} does not exist in new database. If this is a custom permission, you might need to handle it specially.")

    # Migrate Group's Users
    for legacy_user in legacy_group.user_set.all():
        try:
            user = User.objects.get(username=legacy_user.username)
            user.groups.add(new_group)
        except User.DoesNotExist:
            print(f"User {legacy_user.username} not yet migrated or does not exist in the legacy database.")

def run_migration():
    migrate_users()
    migrate_orgaccounts()
    migrate_memberships()
    migrate_group()  # Group migration after users to link them

if __name__ == "__main__":
    run_migration()
