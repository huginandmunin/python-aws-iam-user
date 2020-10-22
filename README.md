# Create and Delete an AWS IAM s3 user

Python scripts for creating and deleting an AWS IAM user with restricted access to a set
of objects stored in an AWS S3 bucket. 

## User Story

You have multiple external users that need access to files that you provide. You would like to use a single S3 bucket for sharing the files. Each user should only have access to their own files. 

## Solution

Access to S3 objects can be controlled by setting up access policies for specific IAM users. Read-access can be restricted to S3 objects that contain a specific string prefix as part of the object name. 

## Implementation

In this implementation the S3 access is granted to objects with a prefix that matches the IAM user name. The objects can appear as files stored in a user directory. For example, S3 objects for a user such as ```dave_1999``` should have names such as

```
dave_1999/file1.txt
dave_1999/file2.txt
...
```

that is, they should start with a prefix and a slash followed by the rest of the file name.

## Create S3 user

The python script ```create_s3_user.py``` implements the IAM user creation with the following steps:

1. Create the IAM user
2. Create an access policy with s3-list and s3-get permissions for this IAM user.
3. Attach the policy to the IAM user
4. Generate an AWS access key pair for the IAM user 
5. Write the key pair to a local CSV file

The script takes the bucket name and IAM user as parameters.

USAGE:
```
python3 create_s3_user.py -b [BUCKET_NAME] -u [USER_NAME]
```

The script does not load any files to the s3 bucket. 

## Delete S3 user

The python script ```delete_s3_user.py``` implements the IAM user deletion with the following steps:

1. Deletes the IAM access keys.
2. Detaches and deletes the policies for the user.
3. Deletes the IAM user
4. Deletes all of the s3 objects for this user 

The script takes the bucket name and IAM user as parameters.

USAGE:
```
python3 delete_s3_user.py -b [BUCKET_NAME] -u [USER_NAME]
```

The script does not delete any local copies of the access-key csv files 
written by ```create_s3_user.py```.

## Utility methods

Most of the utility methods in the module ```s3_user_utils.py``` are 
collected from AWS documentation:
https://docs.aws.amazon.com/code-samples/latest/catalog/code-catalog-python-example_code-iam-iam_basics.html

## Client software interaction with s3-list and s3-get permissions

The user will need s3-get permission to download the files from the s3 bucket. 

An s3-list permission is also granted. This is for users of the WinSCP client. 
WinSCP needs the list permissions in order to locate the 
user files via the bucket-name and prefix. 

WinSCP users can only see their prefix. 
CyberDuck users will see the prefixes of other users (as folders)
but will not be able to view any files for other users. 
