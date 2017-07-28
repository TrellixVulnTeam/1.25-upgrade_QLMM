// Copyright 2015 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package applicationoffers_test

import (
	"fmt"

	"github.com/juju/errors"
	jc "github.com/juju/testing/checkers"
	"github.com/juju/utils/set"
	gc "gopkg.in/check.v1"
	"gopkg.in/juju/charm.v6-unstable"
	"gopkg.in/juju/names.v2"

	"github.com/juju/juju/apiserver/applicationoffers"
	"github.com/juju/juju/apiserver/common"
	"github.com/juju/juju/apiserver/params"
	jujucrossmodel "github.com/juju/juju/core/crossmodel"
	"github.com/juju/juju/permission"
	"github.com/juju/juju/testing"
)

type applicationOffersSuite struct {
	baseSuite
	api *applicationoffers.OffersAPI
}

var _ = gc.Suite(&applicationOffersSuite{})

func (s *applicationOffersSuite) SetUpTest(c *gc.C) {
	s.baseSuite.SetUpTest(c)
	s.applicationOffers = &mockApplicationOffers{}
	getApplicationOffers := func(interface{}) jujucrossmodel.ApplicationOffers {
		return s.applicationOffers
	}

	var err error
	s.api, err = applicationoffers.CreateOffersAPI(
		getApplicationOffers, s.mockState, s.mockStatePool, s.authorizer,
	)
	c.Assert(err, jc.ErrorIsNil)
}

func (s *applicationOffersSuite) assertOffer(c *gc.C, expectedErr error) {
	applicationName := "test"
	s.addApplication(c, applicationName)
	one := params.AddApplicationOffer{
		ModelTag:        testing.ModelTag.String(),
		OfferName:       "offer-test",
		ApplicationName: applicationName,
		Endpoints:       map[string]string{"db": "db"},
	}
	all := params.AddApplicationOffers{Offers: []params.AddApplicationOffer{one}}
	s.applicationOffers.addOffer = func(offer jujucrossmodel.AddApplicationOfferArgs) (*jujucrossmodel.ApplicationOffer, error) {
		c.Assert(offer.OfferName, gc.Equals, one.OfferName)
		c.Assert(offer.ApplicationName, gc.Equals, one.ApplicationName)
		c.Assert(offer.ApplicationDescription, gc.Equals, "A pretty popular blog engine")
		c.Assert(offer.Owner, gc.Equals, "admin")
		c.Assert(offer.HasRead, gc.DeepEquals, []string{"everyone@external"})
		return &jujucrossmodel.ApplicationOffer{}, nil
	}
	charm := &mockCharm{meta: &charm.Meta{Description: "A pretty popular blog engine"}}
	s.mockState.applications = map[string]applicationoffers.Application{
		applicationName: &mockApplication{charm: charm},
	}

	errs, err := s.api.Offer(all)
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(errs.Results, gc.HasLen, len(all.Offers))
	if expectedErr != nil {
		c.Assert(errs.Results[0].Error, gc.ErrorMatches, expectedErr.Error())
		return
	}
	c.Assert(errs.Results[0].Error, gc.IsNil)
	s.applicationOffers.CheckCallNames(c, addOffersBackendCall)
}

func (s *applicationOffersSuite) TestOffer(c *gc.C) {
	s.authorizer.Tag = names.NewUserTag("admin")
	s.assertOffer(c, nil)
}

func (s *applicationOffersSuite) TestOfferPermission(c *gc.C) {
	s.authorizer.Tag = names.NewUserTag("mary")
	s.assertOffer(c, common.ErrPerm)
}

func (s *applicationOffersSuite) TestOfferSomeFail(c *gc.C) {
	s.authorizer.Tag = names.NewUserTag("admin")
	s.addApplication(c, "one")
	s.addApplication(c, "two")
	s.addApplication(c, "paramsfail")
	one := params.AddApplicationOffer{
		ModelTag:        testing.ModelTag.String(),
		OfferName:       "offer-one",
		ApplicationName: "one",
		Endpoints:       map[string]string{"db": "db"},
	}
	bad := params.AddApplicationOffer{
		ModelTag:        testing.ModelTag.String(),
		OfferName:       "offer-bad",
		ApplicationName: "notthere",
		Endpoints:       map[string]string{"db": "db"},
	}
	bad2 := params.AddApplicationOffer{
		ModelTag:        testing.ModelTag.String(),
		OfferName:       "offer-bad",
		ApplicationName: "paramsfail",
		Endpoints:       map[string]string{"db": "db"},
	}
	two := params.AddApplicationOffer{
		ModelTag:        testing.ModelTag.String(),
		OfferName:       "offer-two",
		ApplicationName: "two",
		Endpoints:       map[string]string{"db": "db"},
	}
	all := params.AddApplicationOffers{Offers: []params.AddApplicationOffer{one, bad, bad2, two}}
	s.applicationOffers.addOffer = func(offer jujucrossmodel.AddApplicationOfferArgs) (*jujucrossmodel.ApplicationOffer, error) {
		if offer.ApplicationName == "paramsfail" {
			return nil, errors.New("params fail")
		}
		return &jujucrossmodel.ApplicationOffer{}, nil
	}
	charm := &mockCharm{meta: &charm.Meta{Description: "A pretty popular blog engine"}}
	s.mockState.applications = map[string]applicationoffers.Application{
		"one":        &mockApplication{charm: charm},
		"two":        &mockApplication{charm: charm},
		"paramsfail": &mockApplication{charm: charm},
	}

	errs, err := s.api.Offer(all)
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(errs.Results, gc.HasLen, len(all.Offers))
	c.Assert(errs.Results[0].Error, gc.IsNil)
	c.Assert(errs.Results[3].Error, gc.IsNil)
	c.Assert(errs.Results[1].Error, gc.ErrorMatches, `getting offered application notthere: application "notthere" not found`)
	c.Assert(errs.Results[2].Error, gc.ErrorMatches, `params fail`)
	s.applicationOffers.CheckCallNames(c, addOffersBackendCall, addOffersBackendCall, addOffersBackendCall)
}

func (s *applicationOffersSuite) TestOfferError(c *gc.C) {
	s.authorizer.Tag = names.NewUserTag("admin")
	applicationName := "test"
	s.addApplication(c, applicationName)
	one := params.AddApplicationOffer{
		ModelTag:        testing.ModelTag.String(),
		OfferName:       "offer-test",
		ApplicationName: applicationName,
		Endpoints:       map[string]string{"db": "db"},
	}
	all := params.AddApplicationOffers{Offers: []params.AddApplicationOffer{one}}

	msg := "fail"

	s.applicationOffers.addOffer = func(offer jujucrossmodel.AddApplicationOfferArgs) (*jujucrossmodel.ApplicationOffer, error) {
		return nil, errors.New(msg)
	}
	charm := &mockCharm{meta: &charm.Meta{Description: "A pretty popular blog engine"}}
	s.mockState.applications = map[string]applicationoffers.Application{
		applicationName: &mockApplication{charm: charm},
	}

	errs, err := s.api.Offer(all)
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(errs.Results, gc.HasLen, len(all.Offers))
	c.Assert(errs.Results[0].Error, gc.ErrorMatches, fmt.Sprintf(".*%v.*", msg))
	s.applicationOffers.CheckCallNames(c, addOffersBackendCall)
}

func (s *applicationOffersSuite) assertList(c *gc.C, expectedErr error) {
	s.setupOffers(c, "test")
	filter := params.OfferFilters{
		Filters: []params.OfferFilter{
			{
				OwnerName:       "fred",
				ModelName:       "prod",
				OfferName:       "hosted-db2",
				ApplicationName: "test",
			},
		},
	}
	found, err := s.api.ListApplicationOffers(filter)
	if expectedErr != nil {
		c.Assert(errors.Cause(err), gc.ErrorMatches, expectedErr.Error())
		return
	}
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(found, jc.DeepEquals, params.ListApplicationOffersResults{
		[]params.ApplicationOfferDetails{
			{
				ApplicationOffer: params.ApplicationOffer{
					SourceModelTag:         testing.ModelTag.String(),
					ApplicationDescription: "description",
					OfferName:              "hosted-db2",
					OfferURL:               "fred/prod.hosted-db2",
					Endpoints:              []params.RemoteEndpoint{{Name: "db"}},
					Access:                 "admin",
				},
				CharmName:      "db2",
				ConnectedCount: 5,
			},
		},
	})
	s.applicationOffers.CheckCallNames(c, listOffersBackendCall)
}

func (s *applicationOffersSuite) TestList(c *gc.C) {
	s.authorizer.Tag = names.NewUserTag("admin")
	s.assertList(c, nil)
}

func (s *applicationOffersSuite) TestListPermission(c *gc.C) {
	s.assertList(c, common.ErrPerm)
}

func (s *applicationOffersSuite) TestListError(c *gc.C) {
	s.setupOffers(c, "test")
	s.authorizer.Tag = names.NewUserTag("admin")
	filter := params.OfferFilters{
		Filters: []params.OfferFilter{
			{
				OwnerName:       "fred",
				ModelName:       "prod",
				OfferName:       "hosted-db2",
				ApplicationName: "test",
			},
		},
	}
	msg := "fail"

	s.applicationOffers.listOffers = func(filters ...jujucrossmodel.ApplicationOfferFilter) ([]jujucrossmodel.ApplicationOffer, error) {
		return nil, errors.New(msg)
	}

	_, err := s.api.ListApplicationOffers(filter)
	c.Assert(err, gc.ErrorMatches, fmt.Sprintf(".*%v.*", msg))
	s.applicationOffers.CheckCallNames(c, listOffersBackendCall)
}

func (s *applicationOffersSuite) TestListFilterRequiresModel(c *gc.C) {
	s.setupOffers(c, "test")
	filter := params.OfferFilters{
		Filters: []params.OfferFilter{
			{
				OfferName:       "hosted-db2",
				ApplicationName: "test",
			},
		},
	}
	_, err := s.api.ListApplicationOffers(filter)
	c.Assert(err, gc.ErrorMatches, "application offer filter must specify a model name")
}

func (s *applicationOffersSuite) TestListRequiresFilter(c *gc.C) {
	s.setupOffers(c, "test")
	_, err := s.api.ListApplicationOffers(params.OfferFilters{})
	c.Assert(err, gc.ErrorMatches, "at least one offer filter is required")
}

func (s *applicationOffersSuite) assertShow(c *gc.C, expected []params.ApplicationOfferResult) {
	applicationName := "test"
	filter := params.ApplicationURLs{[]string{"fred/prod.hosted-db2"}}
	anOffer := jujucrossmodel.ApplicationOffer{
		ApplicationName:        applicationName,
		ApplicationDescription: "description",
		OfferName:              "hosted-db2",
		Endpoints:              map[string]charm.Relation{"db": {Name: "db"}},
	}

	s.applicationOffers.listOffers = func(filters ...jujucrossmodel.ApplicationOfferFilter) ([]jujucrossmodel.ApplicationOffer, error) {
		return []jujucrossmodel.ApplicationOffer{anOffer}, nil
	}
	ch := &mockCharm{meta: &charm.Meta{Description: "A pretty popular blog engine"}}
	s.mockState.applications = map[string]applicationoffers.Application{
		applicationName: &mockApplication{charm: ch, curl: charm.MustParseURL("db2-2")},
	}
	s.mockState.model = &mockModel{uuid: testing.ModelTag.Id(), name: "prod", owner: "fred"}
	s.mockState.connStatus = &mockConnectionStatus{count: 5}

	found, err := s.api.ApplicationOffers(filter)
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(found.Results, jc.DeepEquals, expected)
	s.applicationOffers.CheckCallNames(c, listOffersBackendCall)
}

func (s *applicationOffersSuite) TestShow(c *gc.C) {
	expected := []params.ApplicationOfferResult{{
		Result: params.ApplicationOffer{
			SourceModelTag:         testing.ModelTag.String(),
			ApplicationDescription: "description",
			OfferURL:               "fred/prod.hosted-db2",
			OfferName:              "hosted-db2",
			Endpoints:              []params.RemoteEndpoint{{Name: "db"}},
			Access:                 "admin"},
	}}
	s.authorizer.Tag = names.NewUserTag("admin")
	s.assertShow(c, expected)
}

func (s *applicationOffersSuite) TestShowNoPermission(c *gc.C) {
	s.authorizer.Tag = names.NewUserTag("someone")
	expected := []params.ApplicationOfferResult{{
		Error: common.ServerError(errors.NotFoundf("application offer %q", "hosted-db2")),
	}}
	s.assertShow(c, expected)
}

func (s *applicationOffersSuite) TestShowPermission(c *gc.C) {
	user := names.NewUserTag("someone")
	s.authorizer.Tag = user
	expected := []params.ApplicationOfferResult{{
		Result: params.ApplicationOffer{
			SourceModelTag:         testing.ModelTag.String(),
			ApplicationDescription: "description",
			OfferURL:               "fred/prod.hosted-db2",
			OfferName:              "hosted-db2",
			Endpoints:              []params.RemoteEndpoint{{Name: "db"}},
			Access:                 "read"},
	}}
	s.mockState.users.Add(user.Name())
	s.mockState.CreateOfferAccess(names.NewApplicationOfferTag("hosted-db2"), user, permission.ReadAccess)
	s.assertShow(c, expected)
}

func (s *applicationOffersSuite) TestShowError(c *gc.C) {
	url := "fred/prod.hosted-db2"
	filter := params.ApplicationURLs{[]string{url}}
	msg := "fail"

	s.applicationOffers.listOffers = func(filters ...jujucrossmodel.ApplicationOfferFilter) ([]jujucrossmodel.ApplicationOffer, error) {
		return nil, errors.New(msg)
	}
	s.mockState.model = &mockModel{uuid: testing.ModelTag.Id(), name: "prod", owner: "fred"}

	result, err := s.api.ApplicationOffers(filter)
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(result.Results, gc.HasLen, 1)
	c.Assert(result.Results[0].Error, gc.ErrorMatches, fmt.Sprintf(".*%v.*", msg))
	s.applicationOffers.CheckCallNames(c, listOffersBackendCall)
}

func (s *applicationOffersSuite) TestShowNotFound(c *gc.C) {
	urls := []string{"fred/prod.hosted-db2"}
	filter := params.ApplicationURLs{urls}

	s.applicationOffers.listOffers = func(filters ...jujucrossmodel.ApplicationOfferFilter) ([]jujucrossmodel.ApplicationOffer, error) {
		return nil, nil
	}
	s.mockState.model = &mockModel{uuid: testing.ModelTag.Id(), name: "prod", owner: "fred"}

	found, err := s.api.ApplicationOffers(filter)
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(found.Results, gc.HasLen, 1)
	c.Assert(found.Results[0].Error.Error(), gc.Matches, `application offer "hosted-db2" not found`)
	s.applicationOffers.CheckCallNames(c, listOffersBackendCall)
}

func (s *applicationOffersSuite) TestShowErrorMsgMultipleURLs(c *gc.C) {
	urls := []string{"fred/prod.hosted-mysql", "fred/test.hosted-db2"}
	filter := params.ApplicationURLs{urls}

	s.applicationOffers.listOffers = func(filters ...jujucrossmodel.ApplicationOfferFilter) ([]jujucrossmodel.ApplicationOffer, error) {
		return nil, nil
	}
	s.mockState.model = &mockModel{uuid: testing.ModelTag.Id(), name: "prod", owner: "fred"}
	s.mockState.allmodels = []applicationoffers.Model{
		s.mockState.model,
		&mockModel{uuid: "uuid2", name: "test", owner: "fred"},
	}
	anotherState := &mockState{modelUUID: "uuid2"}
	s.mockStatePool.st["uuid2"] = anotherState

	found, err := s.api.ApplicationOffers(filter)
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(found.Results, gc.HasLen, 2)
	c.Assert(found.Results[0].Error.Error(), gc.Matches, `application offer "hosted-mysql" not found`)
	c.Assert(found.Results[1].Error.Error(), gc.Matches, `application offer "hosted-db2" not found`)
	s.applicationOffers.CheckCallNames(c, listOffersBackendCall, listOffersBackendCall)
}

func (s *applicationOffersSuite) TestShowFoundMultiple(c *gc.C) {
	name := "test"
	url := "fred/prod.hosted-" + name
	anOffer := jujucrossmodel.ApplicationOffer{
		ApplicationName:        name,
		ApplicationDescription: "description",
		OfferName:              "hosted-" + name,
		Endpoints:              map[string]charm.Relation{"db": {Name: "db"}},
	}

	name2 := "testagain"
	url2 := "mary/test.hosted-" + name2
	anOffer2 := jujucrossmodel.ApplicationOffer{
		ApplicationName:        name2,
		ApplicationDescription: "description2",
		OfferName:              "hosted-" + name2,
		Endpoints:              map[string]charm.Relation{"db2": {Name: "db2"}},
	}

	filter := params.ApplicationURLs{[]string{url, url2}}

	s.applicationOffers.listOffers = func(filters ...jujucrossmodel.ApplicationOfferFilter) ([]jujucrossmodel.ApplicationOffer, error) {
		c.Assert(filters, gc.HasLen, 1)
		if filters[0].OfferName == "hosted-test" {
			return []jujucrossmodel.ApplicationOffer{anOffer}, nil
		}
		return []jujucrossmodel.ApplicationOffer{anOffer2}, nil
	}
	ch := &mockCharm{meta: &charm.Meta{Description: "A pretty popular blog engine"}}
	s.mockState.applications = map[string]applicationoffers.Application{
		"test": &mockApplication{charm: ch, curl: charm.MustParseURL("db2-2")},
	}
	s.mockState.model = &mockModel{uuid: testing.ModelTag.Id(), name: "prod", owner: "fred"}
	s.mockState.allmodels = []applicationoffers.Model{
		s.mockState.model,
		&mockModel{uuid: "uuid2", name: "test", owner: "mary"},
	}
	s.mockState.connStatus = &mockConnectionStatus{count: 5}

	user := names.NewUserTag("someone")
	s.authorizer.Tag = user
	s.mockState.users.Add(user.Name())
	s.mockState.CreateOfferAccess(names.NewApplicationOfferTag("hosted-test"), user, permission.ReadAccess)

	anotherState := &mockState{
		modelUUID:   "uuid2",
		users:       set.NewStrings(),
		accessPerms: make(map[offerAccess]permission.Access),
	}
	anotherState.applications = map[string]applicationoffers.Application{
		"testagain": &mockApplication{charm: ch, curl: charm.MustParseURL("mysql-2")},
	}
	anotherState.connStatus = &mockConnectionStatus{count: 5}
	anotherState.users.Add(user.Name())
	anotherState.CreateOfferAccess(names.NewApplicationOfferTag("hosted-testagain"), user, permission.ConsumeAccess)
	s.mockStatePool.st["uuid2"] = anotherState

	found, err := s.api.ApplicationOffers(filter)
	c.Assert(err, jc.ErrorIsNil)
	var results []params.ApplicationOffer
	for _, r := range found.Results {
		c.Assert(r.Error, gc.IsNil)
		results = append(results, r.Result)
	}
	c.Assert(results, jc.DeepEquals, []params.ApplicationOffer{
		{
			SourceModelTag:         testing.ModelTag.String(),
			ApplicationDescription: "description",
			OfferName:              "hosted-" + name,
			OfferURL:               url,
			Access:                 "read",
			Endpoints:              []params.RemoteEndpoint{{Name: "db"}}},
		{
			SourceModelTag:         "model-uuid2",
			ApplicationDescription: "description2",
			OfferName:              "hosted-" + name2,
			OfferURL:               url2,
			Access:                 "consume",
			Endpoints:              []params.RemoteEndpoint{{Name: "db2"}}},
	})
	s.applicationOffers.CheckCallNames(c, listOffersBackendCall, listOffersBackendCall)
}

func (s *applicationOffersSuite) assertFind(c *gc.C, expected []params.ApplicationOffer) {
	filter := params.OfferFilters{
		Filters: []params.OfferFilter{
			{
				OfferName: "hosted-db2",
			},
		},
	}
	found, err := s.api.FindApplicationOffers(filter)
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(found, jc.DeepEquals, params.FindApplicationOffersResults{
		Results: expected,
	})
	s.applicationOffers.CheckCallNames(c, listOffersBackendCall)
}

func (s *applicationOffersSuite) TestFind(c *gc.C) {
	s.setupOffers(c, "")
	s.authorizer.Tag = names.NewUserTag("admin")
	expected := []params.ApplicationOffer{
		{
			SourceModelTag:         testing.ModelTag.String(),
			ApplicationDescription: "description",
			OfferName:              "hosted-db2",
			OfferURL:               "fred/prod.hosted-db2",
			Endpoints:              []params.RemoteEndpoint{{Name: "db"}},
			Access:                 "admin"}}
	s.assertFind(c, expected)
}

func (s *applicationOffersSuite) TestFindNoPermission(c *gc.C) {
	s.setupOffers(c, "")
	s.authorizer.Tag = names.NewUserTag("someone")
	s.assertFind(c, []params.ApplicationOffer{})
}

func (s *applicationOffersSuite) TestFindPermission(c *gc.C) {
	s.setupOffers(c, "")
	user := names.NewUserTag("someone")
	s.authorizer.Tag = user
	expected := []params.ApplicationOffer{
		{
			SourceModelTag:         testing.ModelTag.String(),
			ApplicationDescription: "description",
			OfferName:              "hosted-db2",
			OfferURL:               "fred/prod.hosted-db2",
			Endpoints:              []params.RemoteEndpoint{{Name: "db"}},
			Access:                 "read"}}
	s.mockState.users.Add(user.Name())
	s.mockState.CreateOfferAccess(names.NewApplicationOfferTag("hosted-db2"), user, permission.ReadAccess)
	s.assertFind(c, expected)
}

func (s *applicationOffersSuite) TestFindFiltersRequireModel(c *gc.C) {
	s.setupOffers(c, "")
	filter := params.OfferFilters{
		Filters: []params.OfferFilter{
			{
				OfferName:       "hosted-db2",
				ApplicationName: "test",
			}, {
				OfferName:       "hosted-mysql",
				ApplicationName: "test",
			},
		},
	}
	_, err := s.api.FindApplicationOffers(filter)
	c.Assert(err, gc.ErrorMatches, "application offer filter must specify a model name")
}

func (s *applicationOffersSuite) TestFindRequiresFilter(c *gc.C) {
	s.setupOffers(c, "")
	_, err := s.api.FindApplicationOffers(params.OfferFilters{})
	c.Assert(err, gc.ErrorMatches, "at least one offer filter is required")
}

func (s *applicationOffersSuite) TestFindMulti(c *gc.C) {
	db2Offer := jujucrossmodel.ApplicationOffer{
		OfferName:              "hosted-db2",
		ApplicationName:        "db2",
		ApplicationDescription: "db2 description",
		Endpoints:              map[string]charm.Relation{"db": {Name: "db2"}},
	}
	mysqlOffer := jujucrossmodel.ApplicationOffer{
		OfferName:              "hosted-mysql",
		ApplicationName:        "mysql",
		ApplicationDescription: "mysql description",
		Endpoints:              map[string]charm.Relation{"db": {Name: "mysql"}},
	}
	postgresqlOffer := jujucrossmodel.ApplicationOffer{
		OfferName:              "hosted-postgresql",
		ApplicationName:        "postgresql",
		ApplicationDescription: "postgresql description",
		Endpoints:              map[string]charm.Relation{"db": {Name: "postgresql"}},
	}

	s.applicationOffers.listOffers = func(filters ...jujucrossmodel.ApplicationOfferFilter) ([]jujucrossmodel.ApplicationOffer, error) {
		var result []jujucrossmodel.ApplicationOffer
		for _, f := range filters {
			switch f.OfferName {
			case "hosted-db2":
				result = append(result, db2Offer)
			case "hosted-mysql":
				result = append(result, mysqlOffer)
			case "hosted-postgresql":
				result = append(result, postgresqlOffer)
			}
		}
		return result, nil
	}
	ch := &mockCharm{meta: &charm.Meta{Description: "A pretty popular blog engine"}}
	s.mockState.applications = map[string]applicationoffers.Application{
		"db2": &mockApplication{charm: ch, curl: charm.MustParseURL("db2-2")},
	}
	s.mockState.model = &mockModel{uuid: testing.ModelTag.Id(), name: "prod", owner: "fred"}
	s.mockState.connStatus = &mockConnectionStatus{count: 5}

	user := names.NewUserTag("someone")
	s.authorizer.Tag = user
	s.mockState.users.Add(user.Name())
	s.mockState.CreateOfferAccess(names.NewApplicationOfferTag("hosted-db2"), user, permission.ConsumeAccess)

	anotherState := &mockState{
		modelUUID:   "uuid2",
		users:       set.NewStrings(),
		accessPerms: make(map[offerAccess]permission.Access),
	}
	s.mockStatePool.st["uuid2"] = anotherState
	anotherState.applications = map[string]applicationoffers.Application{
		"mysql":      &mockApplication{charm: ch, curl: charm.MustParseURL("mysql-2")},
		"postgresql": &mockApplication{charm: ch, curl: charm.MustParseURL("postgresql-2")},
	}
	anotherState.model = &mockModel{uuid: "uuid2", name: "another", owner: "mary"}
	anotherState.connStatus = &mockConnectionStatus{count: 15}
	anotherState.users.Add(user.Name())
	anotherState.CreateOfferAccess(names.NewApplicationOfferTag("hosted-mysql"), user, permission.ReadAccess)
	anotherState.CreateOfferAccess(names.NewApplicationOfferTag("hosted-postgresql"), user, permission.AdminAccess)

	s.mockState.allmodels = []applicationoffers.Model{
		s.mockState.model,
		anotherState.model,
	}

	filter := params.OfferFilters{
		Filters: []params.OfferFilter{
			{
				OfferName: "hosted-db2",
				OwnerName: "fred",
				ModelName: "prod",
			},
			{
				OfferName: "hosted-mysql",
				OwnerName: "mary",
				ModelName: "another",
			},
			{
				OfferName: "hosted-postgresql",
				OwnerName: "mary",
				ModelName: "another",
			},
		},
	}
	found, err := s.api.FindApplicationOffers(filter)
	c.Assert(err, jc.ErrorIsNil)
	c.Assert(found, jc.DeepEquals, params.FindApplicationOffersResults{
		[]params.ApplicationOffer{
			{
				SourceModelTag:         testing.ModelTag.String(),
				ApplicationDescription: "db2 description",
				OfferName:              "hosted-db2",
				OfferURL:               "fred/prod.hosted-db2",
				Access:                 "consume",
				Endpoints:              []params.RemoteEndpoint{{Name: "db"}},
			},
			{
				SourceModelTag:         "model-uuid2",
				ApplicationDescription: "mysql description",
				OfferName:              "hosted-mysql",
				OfferURL:               "mary/another.hosted-mysql",
				Access:                 "read",
				Endpoints:              []params.RemoteEndpoint{{Name: "db"}},
			},
			{
				SourceModelTag:         "model-uuid2",
				ApplicationDescription: "postgresql description",
				OfferName:              "hosted-postgresql",
				OfferURL:               "mary/another.hosted-postgresql",
				Access:                 "admin",
				Endpoints:              []params.RemoteEndpoint{{Name: "db"}},
			},
		},
	})
	s.applicationOffers.CheckCallNames(c, listOffersBackendCall, listOffersBackendCall)
}

func (s *applicationOffersSuite) TestFindError(c *gc.C) {
	filter := params.OfferFilters{
		Filters: []params.OfferFilter{
			{
				OfferName:       "hosted-db2",
				ApplicationName: "test",
			},
		},
	}
	msg := "fail"

	s.applicationOffers.listOffers = func(filters ...jujucrossmodel.ApplicationOfferFilter) ([]jujucrossmodel.ApplicationOffer, error) {
		return nil, errors.New(msg)
	}
	s.mockState.model = &mockModel{uuid: testing.ModelTag.Id(), name: "prod", owner: "fred"}

	_, err := s.api.FindApplicationOffers(filter)
	c.Assert(err, gc.ErrorMatches, fmt.Sprintf(".*%v.*", msg))
	s.applicationOffers.CheckCallNames(c, listOffersBackendCall)
}

func (s *applicationOffersSuite) TestFindMissingModelInMultipleFilters(c *gc.C) {
	filter := params.OfferFilters{
		Filters: []params.OfferFilter{
			{
				OfferName:       "hosted-db2",
				ApplicationName: "test",
			},
			{
				OfferName:       "hosted-mysql",
				ApplicationName: "test",
			},
		},
	}

	s.applicationOffers.listOffers = func(filters ...jujucrossmodel.ApplicationOfferFilter) ([]jujucrossmodel.ApplicationOffer, error) {
		panic("should not be called")
	}

	_, err := s.api.FindApplicationOffers(filter)
	c.Assert(err, gc.ErrorMatches, "application offer filter must specify a model name")
	s.applicationOffers.CheckCallNames(c)
}
