# Terms

**Pendulum transport**: The communication path carrying existing pendulum commands and returning STM32 status. It does not run the balance loop.

**Neutral confirmation**: A new stopped, linked and unlocked STM32 report received after a neutral frame was sent for the current enable request.

**Session generation**: A connection lifetime used to reject commands created before a disconnect, reconnect or STM32 relock.

**Output lease**: The limited time for which an update from the S3 control loop may be transmitted to the pendulum.
