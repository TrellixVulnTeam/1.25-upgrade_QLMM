// Copyright 2015 Canonical Ltd.
// Licensed under the AGPLv3, see LICENCE file for details.

package azure

import (
	"fmt"
	"math/rand"
	"net/http"
	"time"

	"github.com/Azure/azure-sdk-for-go/arm/resources/resources"
	"github.com/Azure/go-autorest/autorest"
	"github.com/Azure/go-autorest/autorest/to"
	"github.com/juju/errors"
	"github.com/juju/retry"
	"github.com/juju/utils"
	"github.com/juju/utils/clock"
)

const (
	retryDelay       = 5 * time.Second
	maxRetryDelay    = 1 * time.Minute
	maxRetryDuration = 5 * time.Minute
)

func toTags(tags *map[string]*string) map[string]string {
	if tags == nil {
		return nil
	}
	return to.StringMap(*tags)
}

// randomAdminPassword returns a random administrator password for
// Windows machines.
func randomAdminPassword() string {
	// We want at least one each of lower-alpha, upper-alpha, and digit.
	// Allocate 16 of each (randomly), and then the remaining characters
	// will be randomly chosen from the full set.
	validRunes := append(utils.LowerAlpha, utils.Digits...)
	validRunes = append(validRunes, utils.UpperAlpha...)

	lowerAlpha := utils.RandomString(16, utils.LowerAlpha)
	upperAlpha := utils.RandomString(16, utils.UpperAlpha)
	digits := utils.RandomString(16, utils.Digits)
	mixed := utils.RandomString(16, validRunes)
	password := []rune(lowerAlpha + upperAlpha + digits + mixed)
	for i := len(password) - 1; i >= 1; i-- {
		j := rand.Intn(i + 1)
		password[i], password[j] = password[j], password[i]
	}
	return string(password)
}

// callAPIFunc is a function type that should wrap any any
// Azure Resource Manager API calls.
type callAPIFunc func(func() (autorest.Response, error)) error

// backoffAPIRequestCaller is a type whose "call" method can
// be used as a callAPIFunc.
type backoffAPIRequestCaller struct {
	clock clock.Clock
}

// call will call the supplied function, with exponential backoff
// as long as the request returns an http.StatusTooManyRequests
// status.
func (c backoffAPIRequestCaller) call(f func() (autorest.Response, error)) error {
	var resp *http.Response
	return retry.Call(retry.CallArgs{
		Func: func() error {
			autorestResp, err := f()
			resp = autorestResp.Response
			return err
		},
		IsFatalError: func(err error) bool {
			return resp == nil || !autorest.ResponseHasStatusCode(resp, http.StatusTooManyRequests)
		},
		NotifyFunc: func(err error, attempt int) {
			logger.Debugf("attempt %d: %v", attempt, err)
		},
		Attempts:    -1,
		Delay:       retryDelay,
		MaxDelay:    maxRetryDelay,
		MaxDuration: maxRetryDuration,
		BackoffFunc: retry.DoubleDelay,
		Clock:       c.clock,
	})
}

// deleteResource deletes a resource with the given name from the resource
// group, using the provided "Deleter". If the resource does not exist, an
// error satisfying errors.IsNotFound will be returned.
func deleteResource(callAPI callAPIFunc, deleter resourceDeleter, resourceGroup, name string) error {
	var result autorest.Response
	if err := callAPI(func() (autorest.Response, error) {
		var err error
		result, err = deleter.Delete(resourceGroup, name, nil)
		return result, err
	}); err != nil {
		if result.Response != nil && result.StatusCode == http.StatusNotFound {
			return errors.NewNotFound(err, fmt.Sprintf("resource %q not found", name))
		}
		return errors.Annotate(err, "canceling deployment")
	}
	return nil
}

type resourceDeleter interface {
	Delete(resourceGroup, name string, cancel <-chan struct{}) (autorest.Response, error)
}

// collectAPIVersions returns a map of the latest API version for each
// possible resource type. This is needed to use the Azure Resource
// Management API, because the API version requested must match the
// type of the resource being manipulated through the API, rather than
// the API version specified statically in the resource client code.
func collectAPIVersions(callAPI callAPIFunc, mclient resources.ManagementClient) (map[string]string, error) {
	result := make(map[string]string)
	pclient := resources.ProvidersClient{mclient}

	var res resources.ProviderListResult
	err := callAPI(func() (autorest.Response, error) {
		var err error
		res, err = pclient.List(nil)
		return res.Response, err
	})
	if err != nil {
		return result, errors.Trace(err)
	}
	for res.Value != nil {
		for _, provider := range *res.Value {
			if provider.ResourceTypes == nil {
				continue
			}
			for _, resourceType := range *provider.ResourceTypes {
				key := to.String(provider.Namespace) + "/" + to.String(resourceType.ResourceType)
				versions := to.StringSlice(resourceType.APIVersions)
				if len(versions) == 0 {
					continue
				}
				// The versions are newest-first.
				result[key] = versions[0]
			}
		}
		err = callAPI(func() (autorest.Response, error) {
			var err error
			res, err = pclient.ListNextResults(res)
			return res.Response, err
		})
		if err != nil {
			return map[string]string{}, errors.Trace(err)
		}
	}
	return result, nil
}
