# Sliderule Provisioning System (PS) AWS notes

The ps-server functionality to deploy sliderule clusters to AWS is implemented using terraform. When running locally on a desktop/laptop the ps-server runs with aws credentials as described in [aws mfa creds](https://aws.amazon.com/premiumsupport/knowledge-center/authenticate-mfa-cli/).

Use this aws cli command below to obtain credentials to populate your .aws/credentials [default] profile:
<pre>
aws --profile=[Your_Profile_name_here] sts get-session-token --serial-number arn:aws:iam::[your_aws_account_number]:mfa/[your_username] --token-code=[your mfa code here]
</pre>
That command will output something like this:
<pre>
{
    "Credentials": {
        "AccessKeyId": "[a temporary key id]",
        "SecretAccessKey": "[a temporary access key]",
        "SessionToken": "[a temporary session token]",
        "Expiration": "2022-12-03T02:56:23+00:00"
    }
}

</pre>

<pre>
[default]
aws_access_key_id = [from output of get-session-token above]
aws_secret_access_key = [from output get-session-token above]
aws_session_token = [from ouput of get-session-token above]

[Your_Profile_name_here]
aws_access_key_id = [your long term key id here]
aws_secret_access_key = [your long term access key here]
</pre>

The AWS account used to run the ps-server must have at least the privileges needed by the terraform files used to deploy the sliderule cluster. If not the provision commands will fail.

## AWS RDS deploy
The ps-web uses the Django Model abstraction for it's database. Django has a concept of ["migrations"](https://docs.djangoproject.com/en/4.1/topics/migrations/#module-django.db.migrations) for changing the database schema. The migrations are run in the docker-entrypoint.sh. This file is run everytime the ps-web docker container is run. Migration files were copied into the docker container and this will ensure that your aws database will mirror (in schema) your local dev database. You might need to use the --no-input option if you update the models causing a new migration file to be created and django wants you to confirm (this is not every instance; but only for certain circumstances). e.g. It might be because of an added field in a model that requires a default value. This will happen first in your local dev environment and then in your AWS environment. NOTE: consider not using that by default because not having that option when running in development alerts you the the neccessity of using that option when it is time to run in AWS #python manage.py makemigrations --noinput. And in this way your database schema will not change silently and you will be made aware of the change. And this gives you the option to make a change in development that precludes the neccessity of the query by the Django migrations process.

## Bootstrapping the AWS RDS
When you deploy the database for the first time (i.e. without initializing it with a snapshot) the migrations will create the database according to the schema as defined in the migrations. When you modify Django models new migration files get created (and subsequently run) when you re-deploy. The migrations system knows what migrations are already applied and ignores them.

Things to consider are:
* You will need an initial superuser account to login to the admin panel to configure the database with a PS_Developer group and to create developer accounts 

NOTE: PS Developer accounts have is_staff set NOT is_superuser. Regular member accounts have none of those fields set (Regular members include those members designated as owners of organizations).

You will need [ECS Exec](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html) to access the container and perform the one time intialization of the DB. This will require a priviliged account.

The [amazon-ecs-exec-checker](https://github.com/aws-containers/amazon-ecs-exec-checker) tool allows you to verify your accessablity to the ps-web container from your local environment. It will inform you of the neccessary changes that need to be made for ECS Exec to work with your local environment.

See the make target ___ecs-ps-web-shell-testsliderule___ in the ../../test/prov-sys/Makefile to connect to the AWS ECS ps-web container in the the testsliderule.org domain's deployment

</pre>
Once in the container do this:
<pre>
#su reg_user
</pre>
Verify access to the Django system by running the Django manage.py utility:
<pre>
$ python manage.py --help 
</pre>

## One time initialization of the Database
Create the shell session described in the previous section and then follow the instructions outlined in README-provisioning-system.md section titled: "One-time Initialization of the database"