// Copyright 2017 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package oracle

import "github.com/juju/juju/storage"

var (
	DefaultTypes               = []storage.ProviderType{oracleStorageProvideType}
	DefaultStorageProviderType = oracleStorageProvideType
	OracleVolumeType           = oracleVolumeType
	OracleLatencyPool          = latencyPool
	OracleCloudSchema          = cloudSchema
	OracleCredentials          = credentials
	NewOracleVolumeSource      = newOracleVolumeSource
	NewOracleInstance          = newInstance
	GetImageName               = getImageName
	InstanceTypes              = instanceTypes
	FindInstanceSpec           = findInstanceSpec
	ParseImageName             = parseImageName
	CheckImageList             = checkImageList
)
