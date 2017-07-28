#!/bin/bash
# Run the uitests with the juju created from the release tar file
# or from the approximate source of the tar file.

# About SUITE
# We require "TestJujuCore" SUITE to verify Juju's interaction with the GUI.
# The "TestCharm" SUITE verifies charm plugin deps with juju.
# "not TestStorefront" Theoretically work if we accept the consequences
# of building both Juju and the charm plugin with undocumented deps.
# "TestStorefront" fails, maybe because of phantom. firefox reports
# Xvfb did not start, but xfvb works for the win client job.
# SUITE cannot be an empty string if non-essential suites will fail.
# see http://pytest.org/latest/example/markers.html#using-k-expr-to-select-tests-based-on-their-name
# for the syntax supported by $SUITE.

set -eu
export USER=jenkins
export SCRIPTS=$HOME/juju-ci-tools
export RELEASE_TOOLS=$HOME/juju-release-tools
export JUJU_UITEST=$HOME/eco-repos/src/github.com/CanonicalLtd/juju-uitest
export CLOUD_CITY=$HOME/cloud-city
export S3_CONFIG=$CLOUD_CITY/juju-qa.s3cfg
source $CLOUD_CITY/staging-charm-store.rc
set -x

export PATH=/usr/lib/go-1.8/bin:$PATH

REVISION_BUILD=${1:-$revision_build}
SUITE=${2:-TestJujuCore}
JOB_NAME=${3:-juju-with-uitest}
WORKSPACE=${4:-$WORKSPACE}

# Setup a workspace and TMPDIR to keep all test files in one place.
if [[ -z $WORKSPACE || $WORKSPACE == './' || $WORKSPACE == './' ]]; then
    echo "Set a sane WORKSPACE: [$WORKSPACE] is not safe."
    exit 1
fi
WORKSPACE=$(readlink -f $WORKSPACE)
$SCRIPTS/jujuci.py -v setup-workspace $WORKSPACE
export TMPDIR="$WORKSPACE/tmp"
mkdir $TMPDIR

# uitest only supports master and near tip branches.
# This is a design flaw because 1.25 will live a long time and
# we want to catch API breakages with the GUI.
source $($SCRIPTS/s3ci.py get --config $S3_CONFIG $REVISION_BUILD build-revision buildvars.bash)
if [[ $VERSION =~ ^1\..*$ ]]; then
    echo "$VERSION is not supported uitests"
    exit 0
fi

# Print a summary for the jenkins job description.
$SCRIPTS/s3ci.py get-summary $REVISION_BUILD $JOB_NAME

# Get the built version of juju that we want to test with.
JUJU_SOURCE=$($SCRIPTS/s3ci.py get-juju-bin --config $S3_CONFIG $REVISION_BUILD ./)
JUJU_SOURCE_BINARY=$(readlink -f $JUJU_SOURCE)
cd $WORKSPACE

# Get the releases Juju GUI.
GUI_URL=$(sstream-query http://streams.canonical.com/juju/gui/streams/v1/index.json --output-format="%(item_url)s" | head -1)
GUI_ARCHIVE=$(basename $GUI_URL)
wget $GUI_URL

# Create credentials for the TestJujuCore tests.
# We really want a helper script based on deploy_stack.py to create
# an arbitrary temp env from cloud-city.
export JUJU_DATA=$CLOUD_CITY/jes-homes/$JOB_NAME
export JUJU_HOME=$JUJU_DATA
test -d $JUJU_DATA && rm -r $JUJU_DATA
mkdir -p $JUJU_DATA
cat << EOT > $JUJU_DATA/credentials.yaml
credentials:
  google:
    default-region: us-central1
    default-credential: juju-qa
    juju-qa:
      auth-type: jsonfile
      file: $CLOUD_CITY/juju-qa-gce-serviceaccount.json
EOT

# Setup juju-uitest from the local copy.
cp -r $JUJU_UITEST $WORKSPACE/juju-uitest
cd $WORKSPACE/juju-uitest
make


# Do not reveal credentials.
echo "devenv/bin/uitest --driver phantom \
    -c google \
    --gui-archive $WORKSPACE/$GUI_ARCHIVE \
    --credentials <SECRET> \
    --admin <SECRET> \
    --url $STORE_URL" \
    --juju $JUJU_SOURCE_BINARY \
    "$SUITE"
set +x
devenv/bin/uitest --driver phantom \
    -c google \
    --gui-archive $WORKSPACE/$GUI_ARCHIVE \
    --credentials $STORE_CREDENTIALS \
    --admin $STORE_ADMIN \
    --url $STORE_URL \
    --juju $JUJU_SOURCE_BINARY \
    "$SUITE"
