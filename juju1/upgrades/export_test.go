// Copyright 2014 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package upgrades

import "github.com/juju/1.25-upgrade/juju1/environs"

var (
	UpgradeOperations         = &upgradeOperations
	StateUpgradeOperations    = &stateUpgradeOperations
	UbuntuHome                = &ubuntuHome
	RootLogDir                = &rootLogDir
	RootSpoolDir              = &rootSpoolDir
	CharmBundleURL            = &charmBundleURL
	CharmStoragePath          = &charmStoragePath
	StateAddCharmStoragePaths = &stateAddCharmStoragePaths
	NewStateStorage           = &newStateStorage
	StateToolsStorage         = &stateToolsStorage
	AddAZToInstData           = &addAZToInstData

	ChownPath       = &chownPath
	IsLocalEnviron  = &isLocalEnviron
	OsRemove        = &osRemove
	ExecRunCommands = &execRunCommands

	// 118 upgrade functions
	StepsFor118                            = stepsFor118
	EnsureSystemSSHKey                     = ensureSystemSSHKey
	EnsureUbuntuDotProfileSourcesProxyFile = ensureUbuntuDotProfileSourcesProxyFile
	UpdateRsyslogPort                      = updateRsyslogPort
	ProcessDeprecatedEnvSettings           = processDeprecatedEnvSettings
	MigrateLocalProviderAgentConfig        = migrateLocalProviderAgentConfig

	// 121 upgrade functions
	MigrateCharmStorage        = migrateCharmStorage
	MigrateCustomImageMetadata = migrateCustomImageMetadata
	MigrateToolsStorage        = migrateToolsStorage

	// 122 upgrade functions
	EnsureSystemSSHKeyRedux               = ensureSystemSSHKeyRedux
	UpdateAuthorizedKeysForSystemIdentity = updateAuthorizedKeysForSystemIdentity
	AddAvaililityZoneToInstanceData       = addAvaililityZoneToInstanceData

	// 123 upgrade functions
	AddEnvironmentUUIDToAgentConfig = addEnvironmentUUIDToAgentConfig
	AddDefaultStoragePools          = addDefaultStoragePools
	MoveBlocksFromEnvironToState    = moveBlocksFromEnvironToState

	// 124 upgrade functions
	MoveSyslogConfig = moveSyslogConfig
	CopyFile         = copyFile

	// 125 upgrade functions
	AddInstanceTags     = addInstanceTags
	RemoveJujudpass     = removeJujudpass
	AddJujuRegKey       = addJujuRegKey
	CleanToolsStorage   = cleanToolsStorage
	RemoveCharmGetCache = removeCharmGetCache
)

type EnvironConfigUpdater environConfigUpdater
type EnvironConfigReader environConfigReader

func UpgradeEnvironConfig(
	reader EnvironConfigReader,
	updater EnvironConfigUpdater,
	registry environs.ProviderRegistry,
) error {
	return upgradeEnvironConfig(reader, updater, registry)
}
