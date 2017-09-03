# 1.25-upgrade
Tools to upgrade and move a 1.25 environment to a 2.1 controller


## Update MAAS agent name

There's one setting we need to change in MAAS which we can't do in any other way than by using PSQL on the MAAS region controller.

    juju 1.25-upgrade update-maas-agentname <envname>

This will display a command that needs to be run from a shell on the region controller and then wait for the update. Copy the command and run it and the update-maas-agentname command will see the change and finish.


## Initial checks

Verify that you have access to both the source 1.25 environment, and a valid 2.2.3 controller.

    juju 1.25-upgrade verify-source <envname>

Check the status of all the agents.

    juju 1.25-upgrade agent-status <envname>


## Stop all the agents in the source environment.

    juju 1.25-upgrade stop-agents <envname>


## Stop and backup the LXC containers in the source environment.
## Migrate LXC containers in the source environment to LXD.
### Start LXD containers, stop agents


## Import the environment into the controller

    juju 1.25-upgrade import <envname> <controller>

You can see that the model has been created in the target controller by running

    juju models

The new model will be shown as busy until the upgrade is finished and the model is activated.

## Upgrade the agent tools and configuration on the source env machines

    juju 1.25-upgrade upgrade-agents <envname> <controller>

The last step of the `upgrade-agents` command will perform a
connectivity check to ensure that all of the agents can connect to the
target controller API.

## Finalise the import and activate the new model

    juju 1.25-upgrade activate <envname> <controller>

## Start the agents

    juju 1.25-upgrade start-agents <envname>




# In the case of an error during upgrade

Ensure all of the agents are stopped

    juju 1.25-upgrade stop-agents <envname>

Run

    juju 1.25-upgrade abort <envname> <controller>

This will removed the imported model on the target controller (as long
as it wasn't activated), and undo the upgrade-agent steps.

    juju 1.25-upgrade start-agents <envname>
