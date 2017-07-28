# Continuous Integration and Deployment scripts

The Juju QA team uses a few scripts to build release and testing tools
that are placed in private and public clouds. Juju provides several ways
to find tools. The scripts automate and ensure that tools are published
in a consistent manner. These scripts can be adapted to place specific
tools into private clouds.

Get a copy of all the scripts
    lp:juju-release-tools

The general process involves making a release tarball, making a package,
making a tree of tools and metadata, and lastly publishing the tools.
you can skip the tarball and package steps if you just want to publish
the juju tools (AKA jujud, servers, agents). If you want to test a fix
that is in the juju-core trunk branch, you can make your own release
tarball and package.


## Making a release tarball

The Juju QA team tests new revisions of the devel and stable juju-core
branches. The script will create a release tarball without a local copy
of juju-core or any of its dependencies. Anyone with Ubuntu, or possibly
any posix system, can create a release tarball with just this script.

Select a juju-core branch and a revision to create a tarball with
juju-core and all its dependent libraries. This command for example
selects revision 034be9cb of https://github.com/juju/juju
    make-release-tarball.bash 034be9cb https://github.com/juju/juju

The example will create juju-core_1.20.1.tar.gz.

You can pass ‘-1’ as the revision to select tip. The release version is
derived from the source code. If you are making your own release, with
your own changes to the source code, you will need to update the
major.minor.patch versions in the code:
    versions/version.go
    scripts/win-installer/setup.iss


## Making a source package

You can make a package from a release tarball. The script uses
bzr-builddeb and a source package branch to create a either a binary or
source package. This command will create a source package based on the
Ubuntu juju-core source package branch.
    make-package-with-tarball.bash trusty ./juju-core_1.20.1.tar.gz \
        'Full Name <user@example.com>'

The first script argument is any Ubuntu series.

You must provide a proper name and email address to use for the package
changelog. The email address will also be used to select the identity to
sign the source package.


### Creating a binary package for testing

You can create a binary package using the *dsc file created with the
source package on your localhost:
    build-package-with-dsc.bash localhost '' \
        ./tmp.KUVlbtnnet/juju-core_1.20.1-0ubuntu1~14.04.1~juju1.dsc

You can pass
    user@other-host '<extra-ssh-opts>'
to build on a host that provides desired architecture and series


## Assemble the juju tools

Every juju-core package contains a client and a server. The server is
the “juju tool”  that provides the state-server on the bootstrap node
and the agent on the unit nodes. You can create the directory tree of
tools and metadata for a new released by running:
    assemble-public-tools.bash 1.21.1 new-tools/

The script takes two arguments, a release version, and a destination
directory. The new-tools/ directory has 3 or 4 subdirectories for the
phases, debs/, tools/, juju-dist/, and juju-dist-testing/. The script
processes packages, tools, and metadata in several phases:
    1. Collect all the existing public tools from AWS (in tools/)
    2. Download all packages that match the first script argument
       from several archives (to debs/)
    3. Extract the new tools from the debs and add them to existing
       tools (tools/)
    4. Assemble the tools into the simple streams directories (juju-dist/)

If you pass a testing package instead of a release version, it will be
used as the found debian package to extract the tool from. The simple
stream data will be placed in juju-dist-testing/ instead of juju-dist/
to make a clear separation of streams that should not be used in
production. You can pass “ignore” instead of a release version to skip
the the package and extraction steps.


### Assembling tools for a private cloud

If you want to publish a subset of tools, you can manipulate content of
the new-tools/tools/ directory after the first run and rerun the script
with the PRIVATE argument to create a new-tools/juju-dist/ directory
with just the tools you will support in your cloud.
    assemble-public-tools.bash ignore new-tools/ PRIVATE

Thus to assemble the simple streams metadata and tools for 1.20.1, you
would run the script once to get all the tools. Then delete all the
older versions in new-tools/tools. You might even delete the unsupported
architectures such as i386 or arm. Then run the script with the PRIVATE
flag to get just the 1.20.1 tools for amd64.

You can copy your own deb packages to new-tools/debs after the first run
and then run the script again to extract the tools. This would be a
two-phased run of the  script. Run the script once  get all the released
tools.  Then add your own packages and tools and remove the unwanted
tools. Run the script again with the PRIVATE argument to generate a
new-tools/juju-dist/ dir of just what the private cloud wants.


## Publishing tools to a cloud

The publish-public-tools.bash script is used to upload the juju-dist
directory tree to each certified public cloud. It cannot be used by
anyone other than the juju release staff. Anyone can use this script to
develop their own script. Consider the script to be an example of how to
publish to openstack swift, aws s3, and azure storage, for both release
and testing purposes.

Setup a user in your private cloud that will own the public container
that you will publish the tools to. The user’s public container is the
base location used by all juju clients. The container might also be
called the public bucket in some clouds. Create these paths if your
cloud has subcontainers or directories. The paths must be readable by
everyone, but only the owner can make changes:
    juju-dist/
    juju-dist/tools/
    juju-dist/tools/releases/
    juju-dist/tools/streams/
    juju-dist/tools/streams/v1/

The publish_to_canonistack() example shows how upload tools to the
public swift container. The swift client is using these variables
defined in the env: OS_USERNAME, OS_TENANT_NAME, OS_PASSWORD,
OS_AUTH_URL, OS_REGION_NAME, which selects the public container. It
uploads tools to the path that matches to local path (releases/). It
uploads metadata to a path that matches the local path (v1/).


## Configure clients to use the published tools

The juju client is designed to “just work” with public clouds; it knows
how to find public tools from many sources. You can configure the juju
client to look for tools at the location you uploaded them to in  your
private cloud.  From the previous step, the location is the
juju-dist/tools/ path in the public container
    tools-metadata-url: https://<swift.example.com>/v1/<public-container>/juju-dist/tools
