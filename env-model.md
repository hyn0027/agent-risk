## general

```python
Type Env:
    # describe the datamodel. different skills could may resources in their env
    ...

Type SharedEnv:
    TypeFileSystem:
        path: str
        permission: Enum
    fs: FileSystem
    env_var: EnvironmentVariables

ReadOperation:
    operation_name: str
    read_info: data sources described in env that will be read
    require_credentials: credential needed to perform this read operation

WriteOperation:
    operation_name: str
    write_data_model: the datamodel for info that will be written
    sink: which field in env will be changed
    require_credentials: credential needed to perform this write operation
    destructive: bool

ReadAndWriteOperation:
    operation_name: str
    read_info: data sources described in env that will be read
    write_data_model: the datamodel for info that will be written
    sink: which field in env will be changed
    require_credentials: credential needed to perform this read & write operation
    destructive: bool
```

## email skill

```python
Env EmailEnv:
    Type Account:
        Type Folder:
            Type Email:
                Type Body:
                    text
                    attachments: list[Attachment]

                header: Header # from, to, cc, bcc, subject, reply-to, in-reply-to
                body: Body
                flags: Set

            folder_name: str
            emails: list[Email]

        account_name: str
        folders: list[Folder]
    
    Type Config:
        IMAP: IMAPConfig # read email
        SMTP: SMTPConfig # send email
        pswd: PswdConfig # password config
        Gmail: GmailConfig # gmail config
        ICloud: ICloudConfig
        Notmuch: NotmuchConfig # an email indexing and searching tool
        OAuth2: OAuthConfig
        FolderAlias: Dict
        AccountConfig: list[Dict]
        SignatureConfig: list[Dict]
        DownloadConfig: list[Dict]

    accounts: list[Account] # email accounts
    logging: Log # log of the email cli tool
    config: Config

env = EmailEnv()

shared_env = SharedEnv(
    fs = FileSystem(
        Email.config='~/.config/himalaya/config.toml'
    )
    env_var = EnvVar(
        EDITOR='vim'
    )
)


read = ReadOperation(
    operation_name='read',
    read_info=env.accounts[].folders[].emails
    require_credentials=[env.config.IMAP]
)

download_attachment = ReadAndWriteOperation(
    operation_name="download_attachment",
    read_info=env.accounts[].folders[].emails[].body.attachments,
    write_data_model=list[File]
    sink=shared_env.fs,
    require_credentials=[env.config.IMAP, shared_env.fs.permission_to_path],
    destructive: true
)

debugging = ReadOperation(
    operation_name='debugging',
    read_info=env.logging
    require_credentials=[]
)

write_email = WriteOperation(
    operation_name="write_email",
    write_data_model=EmailEnv.Account.Folder.Email,
    sink=env.accounts[].folders[].emails,
    require_credentials=[env.config.SMTP],
    destructive: false
)

reply_email = ReadAndWriteOperation(
    operation_name="reply_email",
    read_info=env.accounts[].folders[].emails[]
    write_data_model=EmailEnv.Account.Folder.Email,
    sink=env.accounts[].folders[].emails,
    require_credentials=[env.config.IMAP, env.config.SMTP],
    destructive: false
) # same is foward email

move_email = WriteOperation(
    operation_name="move_email",
    write_data_model=(source_folder: str, id: int, target_folder: str)
    sink=env.accounts[].folders[].emails,
    require_credentials=[],
    destructive: true
)

copy_email = WriteOperation(
    operation_name="copy_email",
    write_data_model=(source_folder: str, id: int, target_folder: str)
    sink=env.accounts[].folders[].emails,
    require_credentials=[],
    destructive: false
)

delete_email = WriteOperation(
    operation_name="delete_email",
    write_data_model=(folder: str, id: int)
    sink=env.accounts[].folders[].emails,
    require_credentials=[],
    destructive: true
)

add_flags = WriteOperation(
    operation_name="add_flag",
    write_data_model=(folder: str, id: int, flag: str)
    sink=env.accounts[].folders[].emails[].flags,
    require_credentials=[],
    destructive: false
)

remove_flags = WriteOperation(
    operation_name="remove_flag",
    write_data_model=(folder: str, id: int, flag: str)
    sink=env.accounts[].folders[].emails[].flags,
    require_credentials=[],
    destructive: true
)
```

## Booking.com API

6 endpoints:
Read only: Accommodation, cars, attractions(beta) - for searching only
Read&Write: Orders(create/retrieve/cancel), Payment(managing payments), Messaging

```python
send_message = WriteOperation(
    operation_name="send_message",
    write_data_model=(recipient: RecipientID, msg: str)
    sink=env.messages[]
    require_credentials=[booking_API_key],
    destructive: true
)
```

risks/safeguards:

Whenever env.payment_methods is changed or used, require user confirmation if it's above $a_set_amount USD.

info read from emails not from bookings should not flow into booking's message (i.e. block booking's send_message when there are such info read previously and flowed into context)