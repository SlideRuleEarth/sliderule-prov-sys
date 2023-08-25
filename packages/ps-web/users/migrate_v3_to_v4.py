from django.db import migrations, models


def copy_relations(apps, schema_editor):
    '''
        In the example below, this goes between the operations that add a temp field and remove the old field
        This should accurately reflect the transition from a OneToOneField to a ForeignKey for the org field in the Cluster model. Again, apologies for the oversight, and thank you for pointing it out.
        
        We have to hack this in


            operations = [
                migrations.AddField(
                    model_name='cluster',
                    name='org_temp',
                    field=models.ForeignKey(...),
                    ...
                ),

                migrations.RunPython(copy_relations),
                migrations.RunPython(migrate_data_forward),


                migrations.RemoveField(
                    model_name='cluster',
                    name='org',
                ),
                migrations.RenameField(
                    model_name='cluster',
                    old_name='org_temp',
                    new_name='org'
                )
            ]
    '''
    Cluster = apps.get_model('users', 'Cluster')
    OrgAccount = apps.get_model('users', 'OrgAccount')
    
    for org_account in OrgAccount.objects.all():
        try:
            cluster = org_account.cluster
            cluster.org = org_account
            cluster.save()
        except Cluster.DoesNotExist:
            pass  # No associated Cluster for this OrgAccount



def migrate_data_forward(apps, schema_editor):
    OrgAccount = apps.get_model('users', 'OrgAccount')
    Cluster = apps.get_model('users', 'Cluster')

    for org_account in OrgAccount.objects.all():
        # Assuming you have a ForeignKey from Cluster to OrgAccount
        cluster = org_account.cluster_set.first()  # Get the first (i.e. only) Cluster associated with this OrgAccount

        if cluster:
            # Copy data from OrgAccount to Cluster
            cluster.max_allowance = org_account.max_allowance
            cluster.monthly_allowance = org_account.monthly_allowance
            cluster.balance = org_account.balance
            cluster.fytd_accrued_cost = org_account.fytd_accrued_cost
            cluster.creation_date = org_account.creation_date
            cluster.modified_date = org_account.modified_date
            cluster.node_mgr_fixed_cost = org_account.node_mgr_fixed_cost
            cluster.node_fixed_cost = org_account.node_fixed_cost
            cluster.desired_num_nodes = org_account.desired_num_nodes
            cluster.max_hrly = org_account.max_hrly
            cluster.cur_hrly = org_account.cur_hrly
            cluster.min_hrly = org_account.min_hrly
            cluster.min_ddt = org_account.min_ddt
            cluster.cur_ddt = org_account.cur_ddt
            cluster.max_ddt = org_account.max_ddt
            cluster.fc_min_hourly = org_account.fc_min_hourly
            cluster.fc_min_daily = org_account.fc_min_daily
            cluster.fc_min_monthly = org_account.fc_min_monthly
            cluster.fc_cur_hourly = org_account.fc_cur_hourly
            cluster.fc_cur_daily = org_account.fc_cur_daily
            cluster.fc_cur_monthly = org_account.fc_cur_monthly
            cluster.fc_max_hourly = org_account.fc_max_hourly
            cluster.fc_max_daily = org_account.fc_max_daily
            cluster.fc_max_monthly = org_account.fc_max_monthly
            cluster.version = org_account.version
            cluster.admin_max_node_cap = org_account.admin_max_node_cap
            cluster.time_to_live_in_mins = org_account.time_to_live_in_mins
            cluster.allow_deploy_by_token = org_account.allow_deploy_by_token
            cluster.destroy_when_no_nodes = org_account.destroy_when_no_nodes
            cluster.is_public = org_account.is_public
            cluster.pcqr_display_age_in_hours = org_account.pcqr_display_age_in_hours
            cluster.pcqr_retention_age_in_days = org_account.pcqr_retention_age_in_days
            cluster.loop_count = org_account.loop_count
            cluster.num_owner_ps_cmd = org_account.num_owner_ps_cmd
            cluster.num_ps_cmd = org_account.num_ps_cmd
            cluster.num_ps_cmd_successful = org_account.num_ps_cmd_successful
            cluster.num_onn = org_account.num_onn
            cluster.provisioning_suspended = org_account.provisioning_suspended
            cluster.num_setup_cmd = org_account.num_setup_cmd
            cluster.num_setup_cmd_successful = org_account.num_setup_cmd_successful

            cluster.save()

class Migration(migrations.Migration):

    dependencies = [
        # ...
    ]

    operations = [
        migrations.RunPython(migrate_data_forward),
        # ... (other operations) ...
    ]
