import argparse
import csv
import datetime
from datetime import date
import json
import logging
import re
import time

import boto3
from botocore.exceptions import ClientError

import s3_user_utils

logger = logging.getLogger(__name__)
iam = boto3.resource('iam')


def create_s3_user():
    """
    Create an IAM user with read-only access for their s3 folder (s3-prefix).

    The user_name is a string, such as
    'Dave', 'hal-9000', or 'Richard_Strauss_07111864'. 
    Only letters, numbers, underscores, and dashes are allowed. 
    The minimum string length is 1.
    The s3 object names for this user should have a prefix that matches their user name. 

    This script does not create any s3 buckets or populate any s3 folders.

    USAGE:
    python create_s3_user.py -b [BUCKET_NAME] -u [USER_NAME]
    """

    # Set up logging
    run_date = f'{date.today().strftime("%Y%m%d")}'
    log_filename = f'create_s3_user_{run_date}.log'
    logging.basicConfig(filename=log_filename, level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
    logger = logging.getLogger()

    # Define input arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--bucket_name", default=None,  dest='bucket_name', required=True,
                help="The name of the s3 bucket.")
    parser.add_argument("-u", "--user_name", default=None,  dest='user_name', required=True,
                help="The name for the iam-user.")

    # Parse input args
    args = parser.parse_args()
    bucket_name = args.bucket_name
    user_name = args.user_name
    logger.info(f'Creating iam-user {user_name} for bucket {bucket_name}')

    try:
        # Validate the bucket name and user name
        if not s3_user_utils.bucket_exists(bucket_name):
            exit_program(f'Bucket does not exist: {bucket_name}')
        if not is_valid_user_name(user_name):
            exit_program(f'Invalid user name: {user_name}. Only letters, numbers, underscores, and dashes are allowed.')

        # Exit if the user name is already in use for this account
        for existing_user in s3_user_utils.list_users():
            if user_name == existing_user.name:
                exit_program(f'This user already exists in the account: {user_name}')

        # Create the new iam user
        user = s3_user_utils.create_user(user_name)

        # Create s3 list- and get-policies and attach to user
        create_and_add_policies(user, bucket_name)

        # Generate user keys and write to local csv file
        key_pair = s3_user_utils.create_key(user_name)
        write_keys_to_csv(user_name,key_pair)

    except Exception as e:
        error_message = "Error of type {0} occurred:{1!r}".format(type(e).__name__, str(e))
        logger.error(error_message)
        exit_program(error_message)

    else:    
        print('Success!')


def create_and_add_policies(user, bucket_name):
    """
    Create and add policies such that users can only view (s3-ListBucket) 
    and download items (s3-GetOBject) from their personal folder (the s3 prefix).

    For the purposes of this demo we will create new policies for the new user.
    In production we would have a single durable policy that reads the 'aws:username' variable.
    """
    logger.info(f'Creating list and get policies for bucket {bucket_name}')

    # Create and add the list policy
    policy_name = s3_user_utils.user_policy_name(user.user_name, 'list')
    policy_description = 'Grant permission to list bucket for user folder'
    action = 's3:ListBucket'
    if policy_exists(policy_name):
        exit_program(f'Cannot create policy because it already exists: {policy_name}')
    list_policy = create_policy(
        policy_name, policy_description,
        action, bucket_name, user.name)
    s3_user_utils.attach_policy(user.name, list_policy.arn)

    # Create and add the get policy
    policy_name = s3_user_utils.user_policy_name(user.user_name, 'get')   
    policy_description = 'Grant permission to get objects from users folder'
    action = 's3:GetObject'
    if policy_exists(policy_name):
        exit_program(f'Cannot create policy because it already exists: {policy_name}')       
    get_policy = create_policy(
        policy_name, policy_description,
        action, bucket_name, user.name)
    s3_user_utils.attach_policy(user.name, get_policy.arn)


def create_policy(name, description, actions, bucket_name, user_name):
    """
    Creates a policy that contains a single statement. 

    For ListBucket and GetObject policies the user will have permissions for only
    their s3 folder. 

    For ListBucket the permission restriction is done via a policy condition. 
    This works with the CyberDuck client but not WinSCP. 

    For GetObject the restriction is specified in the resource arn. 

    :param name: The name of the policy to create.
    :param description: The description of the policy.
    :param actions: The actions allowed by the policy. For this demo we are looking for
                    's3-ListBucket' and 's3-GetObject'.
    :param bucket_name: The bucket name will be used to create the Amazon Resource Name (ARN) 
                        of the resource that this policy applies to. 
    :param user_name: The iam user name that matches the user folder in s3.
    :return: The newly created policy.
    """

    # For the s3 getobject we add the user folder to the resource arn
    if actions == 's3:GetObject':
        resource_arn = f'arn:aws:s3:::{bucket_name}/{user_name}/*'
    else:
        resource_arn = f'arn:aws:s3:::{bucket_name}'

    # Create the policy json
    policy_doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": actions,
                "Resource": resource_arn,
            }
        ]
    }

    # For the s3 listbucket we add a condition to restrict to listing the user's folder
    if actions == 's3:ListBucket':
        user_folder = f'{user_name}/'
        condition = { 
                        "Condition":{
                            "StringEquals": {
                                "s3:prefix": [
                                    "",
                                    user_folder
                                ],
                                "s3:delimiter": [
                                    "/"
                                ]
                            }
                        }
                    }
        # Update the statement dictionary with the condition
        policy_doc['Statement'][0].update(condition)

    logger.info(f'Policy doc: {policy_doc}')
    try:
        policy = iam.create_policy(
            PolicyName=name, Description=description,
            PolicyDocument=json.dumps(policy_doc))
        logger.info(f'Created policy {policy.arn}')
    except ClientError:
        logger.exception(f"Couldn't create policy {name}")
        raise
    else:
        return policy


def policy_exists(policy_name):
    """
    Returns true if the desired policy name is already in use in this account.
    """
    policy_exists = False
    # Here we use 'Local' to search in locally managed policies, not AWS managed policies
    for policy in s3_user_utils.list_policies('Local'):
        if policy_name == policy.policy_name:
            policy_exists = True
            break
    return policy_exists


def is_valid_user_name(user_name):
    """
    Returns true if the user name is composed of one or more 
    letters, numbers, underscores, and dashes.
    """
    is_valid = True if re.match("^[A-Za-z0-9_-]+$", user_name) else False
    return is_valid


def write_keys_to_csv(user_name, key_pair):
    """
    Write the key pair into a local csv file with name 'user_name_accessKeys.csv'.
    """
    if key_pair is None:
        exit_program(f'No keys available to save to csv for user {user_name}')

    key_info = [
        ['Access key ID', 'Secret access key'],
        [key_pair.id, key_pair.secret]
    ]
    csv_filename = f'{user_name}_accessKeys.csv'
    with open(csv_filename , 'w', newline='\n', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        for row in key_info:
            writer.writerow(row)
    csvfile.close
    logger.info(f'Wrote keys to file {csv_filename}.')


def exit_program(message):
    """
    Write error message to the log file and the console and exit.
    """
    logger.error(f'Exiting. {message}')
    print(f'ERROR. Exiting. {message}')
    exit(0)


if __name__ == '__main__':
    create_s3_user()