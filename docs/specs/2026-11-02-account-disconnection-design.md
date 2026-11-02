# Account disconnection without job deletion

## Goal

Allow a connected account to be disconnected even when synchronization jobs
refer to it. Disconnecting an account must not delete those jobs.

## Behavior

- Account disconnection remains unavailable while a synchronization or another
  account operation is active.
- Confirming disconnection removes the selected connection and its stored
  credentials.
- Every remote job that referred to the removed connection is preserved.
- Preserved jobs are disabled and have no assigned connection.
- Synchronization groups, local and remote paths, backup settings, direction,
  verification settings, and other job properties remain unchanged.
- A disconnected job remains visible and is labelled as having no connected
  account.
- A disconnected job cannot run until the user assigns an available account.
- Assigning an account and saving the job makes it valid again; the user may
  then enable it explicitly.
- Remote files and snapshots are not deleted by account disconnection.

## Configuration model

`RemoteJobConfig.connection_id` supports an empty value to represent a
recoverable disconnected job. A non-empty value must still reference an
existing connection. Newly created or enabled jobs must have a connection.

Configuration loading and saving preserve disconnected jobs. Existing valid
configurations remain compatible without migration.

## Service transaction

The disconnect operation updates the saved configuration only after credential
removal succeeds. The saved update removes the connection and atomically
detaches and disables its jobs. If credential removal fails, the connection and
jobs remain unchanged and the error is shown to the user.

## User interface

The confirmation message explains that associated jobs will be kept but
disabled. Synchronization views and editors render disconnected jobs without
assuming a connection exists. The editor allows selecting a replacement
account, but saving or enabling a job without one produces a clear validation
message.

## Verification

Automated tests cover:

- disconnecting an unused account;
- disconnecting an account used by one or more jobs;
- preserving job IDs and settings while clearing the connection and disabling
  the jobs;
- preserving synchronization-group references;
- rejecting execution of a disconnected job;
- displaying and editing a disconnected job safely;
- leaving configuration unchanged when credential removal fails;
- loading legacy valid configurations unchanged.
