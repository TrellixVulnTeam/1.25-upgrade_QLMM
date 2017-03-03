// Copyright 2012-2015 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package apicaller

import (
	"fmt"

	jc "github.com/juju/testing/checkers"
	"github.com/juju/utils"
	gc "gopkg.in/check.v1"

	"github.com/juju/1.25-upgrade/juju1/agent"
	"github.com/juju/1.25-upgrade/juju1/api"
	"github.com/juju/1.25-upgrade/juju1/apiserver/common"
	"github.com/juju/1.25-upgrade/juju1/apiserver/params"
	"github.com/juju/1.25-upgrade/juju1/state/multiwatcher"
	coretesting "github.com/juju/1.25-upgrade/juju1/testing"
	"github.com/juju/1.25-upgrade/juju1/worker"
)

type OpenAPIStateSuite struct {
	coretesting.BaseSuite
}

var _ = gc.Suite(&OpenAPIStateSuite{})

func (s *OpenAPIStateSuite) SetUpTest(c *gc.C) {
	s.BaseSuite.SetUpTest(c)
	s.PatchValue(&checkProvisionedStrategy, utils.AttemptStrategy{})
}

func (s *OpenAPIStateSuite) TestOpenAPIStateReplaceErrors(c *gc.C) {
	type replaceErrors struct {
		openErr    error
		replaceErr error
	}
	var apiError error
	s.PatchValue(&apiOpen, func(info *api.Info, opts api.DialOpts) (api.Connection, error) {
		return nil, apiError
	})
	errReplacePairs := []replaceErrors{{
		fmt.Errorf("blah"), nil,
	}, {
		openErr:    &params.Error{Code: params.CodeNotProvisioned},
		replaceErr: worker.ErrTerminateAgent,
	}, {
		openErr:    &params.Error{Code: params.CodeUnauthorized},
		replaceErr: worker.ErrTerminateAgent,
	}}
	for i, test := range errReplacePairs {
		c.Logf("test %d", i)
		apiError = test.openErr
		_, err := OpenAPIState(fakeAgent{})
		if test.replaceErr == nil {
			c.Check(err, gc.Equals, test.openErr)
		} else {
			c.Check(err, gc.Equals, test.replaceErr)
		}
	}
}

func (s *OpenAPIStateSuite) TestOpenAPIStateWaitsProvisioned(c *gc.C) {
	s.PatchValue(&checkProvisionedStrategy.Min, 5)
	var called int
	s.PatchValue(&apiOpen, func(info *api.Info, opts api.DialOpts) (api.Connection, error) {
		called++
		if called == checkProvisionedStrategy.Min-1 {
			return nil, &params.Error{Code: params.CodeUnauthorized}
		}
		return nil, &params.Error{Code: params.CodeNotProvisioned}
	})
	_, err := OpenAPIState(fakeAgent{})
	c.Assert(err, gc.Equals, worker.ErrTerminateAgent)
	c.Assert(called, gc.Equals, checkProvisionedStrategy.Min-1)
}

func (s *OpenAPIStateSuite) TestOpenAPIStateWaitsProvisionedGivesUp(c *gc.C) {
	s.PatchValue(&checkProvisionedStrategy.Min, 5)
	var called int
	s.PatchValue(&apiOpen, func(info *api.Info, opts api.DialOpts) (api.Connection, error) {
		called++
		return nil, &params.Error{Code: params.CodeNotProvisioned}
	})
	_, err := OpenAPIState(fakeAgent{})
	c.Assert(err, gc.Equals, worker.ErrTerminateAgent)
	// +1 because we always attempt at least once outside the attempt strategy
	// (twice if the API server initially returns CodeUnauthorized.)
	c.Assert(called, gc.Equals, checkProvisionedStrategy.Min+1)
}

func (s *OpenAPIStateSuite) TestOpenAPIStateUsesOldPwd(c *gc.C) {
	currentPwd := "current"
	oldPwd := "old"

	var apiError error
	s.PatchValue(&apiOpen, func(info *api.Info, opts api.DialOpts) (api.Connection, error) {
		if info.Password != oldPwd {
			return nil, apiError
		}
		return nil, nil
	})

	// If we receive these errors, we should try to login using old password
	fallthroughErrors := []error{common.ErrBadCreds, &params.Error{Code: params.CodeUnauthorized}}
	info := &api.Info{Password: currentPwd}

	for i, errFallthrough := range fallthroughErrors {
		c.Logf("test %d", i)
		apiError = errFallthrough
		_, usedOldPassword, err := openAPIStateUsingInfo(info, oldPwd)
		c.Assert(err, jc.ErrorIsNil)
		c.Assert(usedOldPassword, jc.IsTrue)
	}
}

type fakeAgent struct {
	agent.Agent
}

func (fakeAgent) CurrentConfig() agent.Config {
	return fakeAPIOpenConfig{}
}

type fakeAPIOpenConfig struct {
	agent.Config
}

func (fakeAPIOpenConfig) APIInfo() (*api.Info, bool)      { return &api.Info{}, true }
func (fakeAPIOpenConfig) OldPassword() string             { return "old" }
func (fakeAPIOpenConfig) Jobs() []multiwatcher.MachineJob { return []multiwatcher.MachineJob{} }
