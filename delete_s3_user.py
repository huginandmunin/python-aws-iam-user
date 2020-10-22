import argparse
import datetime
from datetime import date
import logging
import boto3
from botocore.exceptions import ClientError

import s3_user_utils

logger = logging.getLogger(__name__)
iam = boto3.client('iam')
s3 = boto3.resource('s3')


def delete_s3_user():
    """
    Delete the IAM user and associated resources created by create_s3_user.
    Items to delete are:
    - the iam user
    - the user policies
    - the S3 access keys
    - the objects in S3 stored for this user

    USAGE:
    python delete_s3_user.py -b [BUCKET_NAME] -u [USER_NAME]
    """

    # Set up logging
    run_date = f'{date.today().strftime("%Y%m%d")}'
    log_filename = f'delete_s3_user_{run_date}.log'
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
    logger.info(f'Deleting iam-user {user_name} for bucket {bucket_name}.')

    try:
        # Find and delete access keys for user
        all_keys_for_user = s3_user_utils.list_keys(user_name)
        if all_keys_for_user:
            for key in all_keys_for_user:
                logger.info(f'Deleting key {key.id} for user {user_name}.')
                s3_user_utils.delete_key(user_name, key.id)
        else:
            logger.warning(f'No access keys found for user {user_name}.')

        # Detach and delete policies
        listed_policies = s3_user_utils.list_policies('Local')
        user_policy_names = [ s3_user_utils.user_policy_name(user_name, 'list'), 
                              s3_user_utils.user_policy_name(user_name, 'get')]
        for user_policy_name in user_policy_names:
            found_policy = False
            for policy in listed_policies:
                if policy.policy_name == user_policy_name:
                    found_policy = True
                    logger.info(f'Deleting policy {user_policy_name} for user {user_name}.')
                    s3_user_utils.detach_policy(user_name,policy.arn)
                    s3_user_utils.delete_policy(policy.arn)      
            if not found_policy:
                logger.warning(f'Cannot find policy to remove: {user_policy_name}.')

        # Delete iam user
        logger.info(f'Deleting user {user_name}')
        s3_user_utils.delete_user(user_name)

        # Check that the bucket exists
        if not s3_user_utils.bucket_exists(bucket_name):
            exit_program(f'Bucket does not exist: {bucket_name}')

        # Delete s3-objects for user
        logger.info(f'Deleting objects for user {user_name} in bucket {bucket_name}.')
        bucket = s3.Bucket(bucket_name)
        prefix = f'{user_name}/'
        # Count objects to delete
        user_object_count = 0
        for key in bucket.objects.filter(Prefix=prefix):
            user_object_count += 1
        if user_object_count > 0:
            logger.info(f'Number of ojects to delete: {user_object_count}')
            # Delete objects with the user-name prefix
            # https://stackoverflow.com/questions/11426560/amazon-s3-boto-how-to-delete-folder
            bucket.objects.filter(Prefix=prefix).delete()
        else:
            logger.warning(f'No objects found for user {user_name} in bucket {bucket_name}.')
        
    except Exception as e:
        error_message = "Error of type {0} occurred:{1!r}".format(type(e).__name__, str(e))
        logger.error(error_message)
        exit_program(error_message)

    else:    
        print('Success!')


def exit_program(message):
    """
    Write error message to the log file and the console and exit.
    """
    logger.error(f'Exiting. {message}')
    print(f'ERROR. Exiting. {message}')
    exit(0)


if __name__ == '__main__':
    delete_s3_user()