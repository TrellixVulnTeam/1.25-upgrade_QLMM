// Copyright 2014 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package testing

import (
	jujutesting "github.com/juju/testing"
	jc "github.com/juju/testing/checkers"
	"github.com/juju/utils/clock"
	gc "gopkg.in/check.v1"
	"gopkg.in/juju/names.v2"

	"github.com/juju/juju/cloud"
	"github.com/juju/juju/environs/config"
	"github.com/juju/juju/mongo"
	"github.com/juju/juju/mongo/mongotest"
	"github.com/juju/juju/state"
	"github.com/juju/juju/storage"
	"github.com/juju/juju/storage/provider"
	dummystorage "github.com/juju/juju/storage/provider/dummy"
	"github.com/juju/juju/testing"
)

type InitializeArgs struct {
	Owner                     names.UserTag
	InitialConfig             *config.Config
	ControllerInheritedConfig map[string]interface{}
	RegionConfig              cloud.RegionConfig
	NewPolicy                 state.NewPolicyFunc
	Clock                     clock.Clock
}

// Initialize initializes the state and returns it. If state was not
// already initialized, and cfg is nil, the minimal default model
// configuration will be used.
// This provides for tests still using a real clock from utils as tests are
// migrated to use the testing clock
func Initialize(c *gc.C, owner names.UserTag, cfg *config.Config, controllerInheritedConfig map[string]interface{}, regionConfig cloud.RegionConfig, newPolicy state.NewPolicyFunc) *state.State {
	return InitializeWithArgs(c, InitializeArgs{
		Owner:                     owner,
		InitialConfig:             cfg,
		ControllerInheritedConfig: controllerInheritedConfig,
		RegionConfig:              regionConfig,
		NewPolicy:                 newPolicy,
		Clock:                     &clock.WallClock,
	})
}

// InitializeWithArgs initializes the state and returns it. If state was not
// already initialized, and args.Config is nil, the minimal default model
// configuration will be used.
func InitializeWithArgs(c *gc.C, args InitializeArgs) *state.State {
	if args.InitialConfig == nil {
		args.InitialConfig = testing.ModelConfig(c)
	}
	mgoInfo := NewMongoInfo()
	dialOpts := mongotest.DialOpts()

	controllerCfg := testing.FakeControllerConfig()
	st, err := state.Initialize(state.InitializeParams{
		Clock:            args.Clock,
		ControllerConfig: controllerCfg,
		ControllerModelArgs: state.ModelArgs{
			CloudName:   "dummy",
			CloudRegion: "dummy-region",
			Config:      args.InitialConfig,
			Owner:       args.Owner,
			StorageProviderRegistry: StorageProviders(),
		},
		ControllerInheritedConfig: args.ControllerInheritedConfig,
		Cloud: cloud.Cloud{
			Name:      "dummy",
			Type:      "dummy",
			AuthTypes: []cloud.AuthType{cloud.EmptyAuthType},
			Regions: []cloud.Region{
				cloud.Region{
					Name:             "dummy-region",
					Endpoint:         "dummy-endpoint",
					IdentityEndpoint: "dummy-identity-endpoint",
					StorageEndpoint:  "dummy-storage-endpoint",
				},
				cloud.Region{
					Name:             "nether-region",
					Endpoint:         "nether-endpoint",
					IdentityEndpoint: "nether-identity-endpoint",
					StorageEndpoint:  "nether-storage-endpoint",
				},
				cloud.Region{
					Name:             "unused-region",
					Endpoint:         "unused-endpoint",
					IdentityEndpoint: "unused-identity-endpoint",
					StorageEndpoint:  "unused-storage-endpoint",
				},
			},
			RegionConfig: args.RegionConfig,
		},
		MongoInfo:     mgoInfo,
		MongoDialOpts: dialOpts,
		NewPolicy:     args.NewPolicy,
	})
	c.Assert(err, jc.ErrorIsNil)
	return st
}

func StorageProviders() storage.ProviderRegistry {
	return storage.ChainedProviderRegistry{
		storage.StaticProviderRegistry{
			map[storage.ProviderType]storage.Provider{
				"static": &dummystorage.StorageProvider{IsDynamic: false},
				"environscoped": &dummystorage.StorageProvider{
					StorageScope: storage.ScopeEnviron,
					IsDynamic:    true,
				},
				"environscoped-block": &dummystorage.StorageProvider{
					StorageScope: storage.ScopeEnviron,
					IsDynamic:    true,
					SupportsFunc: func(k storage.StorageKind) bool {
						return k == storage.StorageKindBlock
					},
				},
				"machinescoped": &dummystorage.StorageProvider{
					StorageScope: storage.ScopeMachine,
					IsDynamic:    true,
				},
			},
		},
		provider.CommonStorageProviders(),
	}
}

// NewMongoInfo returns information suitable for
// connecting to the testing controller's mongo database.
func NewMongoInfo() *mongo.MongoInfo {
	return &mongo.MongoInfo{
		Info: mongo.Info{
			Addrs:  []string{jujutesting.MgoServer.Addr()},
			CACert: testing.CACert,
		},
	}
}

// NewState initializes a new state with default values for testing and
// returns it.
func NewState(c *gc.C) *state.State {
	owner := names.NewLocalUserTag("test-admin")
	cfg := testing.ModelConfig(c)
	newPolicy := func(*state.State) state.Policy { return &MockPolicy{} }
	return Initialize(c, owner, cfg, nil, nil, newPolicy)
}
