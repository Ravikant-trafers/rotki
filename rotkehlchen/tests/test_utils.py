import json
import time
from unittest.mock import patch

import pytest

from rotkehlchen.errors import ConversionError, UnprocessableTradePair
from rotkehlchen.exchanges.data_structures import invert_pair
from rotkehlchen.fval import FVal
from rotkehlchen.serialization.serialize import process_result
from rotkehlchen.tests.utils.mock import MockResponse
from rotkehlchen.utils.interfaces import CacheableObject, cache_response_timewise
from rotkehlchen.utils.misc import (
    combine_dicts,
    combine_stat_dicts,
    convert_to_int,
    iso8601ts_to_timestamp,
)
from rotkehlchen.utils.version_check import check_if_version_up_to_date


def test_process_result():
    d = {
        'overview': {
            'foo': FVal(1.0),
        },
        'all_events': {
            'boo': FVal(1.0),
            'something': [
                {'a': 'a', 'f': FVal(1.0)},
                {'b': 'b', 'f': FVal(2.0)},
            ],
        },
    }

    # Without process result should throw an error but with it no
    with pytest.raises(TypeError):
        json.dumps(d)

    json.dumps(process_result(d))


def test_tuple_in_process_result():
    d = {'overview': [{'foo': (FVal('0.1'),)}]}

    # Process result should detect the tuple and throw
    with pytest.raises(ValueError):
        json.dumps(process_result(d))


def test_iso8601ts_to_timestamp():
    assert iso8601ts_to_timestamp('2018-09-09T12:00:00.000Z') == 1536494400
    assert iso8601ts_to_timestamp('2011-01-01T04:13:22.220Z') == 1293855202
    assert iso8601ts_to_timestamp('1986-11-04T16:23:57.921Z') == 531505438
    # Timezone specific part of the test
    timezone_ts_str = '1997-07-16T22:30'
    timezone_ts_at_utc = 869092200
    assert iso8601ts_to_timestamp(timezone_ts_str + 'Z') == timezone_ts_at_utc
    # The utc offset for July should be time.altzone since it's in DST
    # https://stackoverflow.com/questions/3168096/getting-computers-utc-offset-in-python
    utc_offset = time.altzone
    assert iso8601ts_to_timestamp(timezone_ts_str) == timezone_ts_at_utc + utc_offset
    assert iso8601ts_to_timestamp('1997-07-16T22:30+01:00') == 869088600
    assert iso8601ts_to_timestamp('1997-07-16T22:30:45+01:00') == 869088645
    assert iso8601ts_to_timestamp('1997-07-16T22:30:45.1+01:00') == 869088645
    assert iso8601ts_to_timestamp('1997-07-16T22:30:45.01+01:00') == 869088645
    assert iso8601ts_to_timestamp('1997-07-16T22:30:45.001+01:00') == 869088645
    assert iso8601ts_to_timestamp('1997-07-16T22:30:45.9+01:00') == 869088646
    assert iso8601ts_to_timestamp('1997-07-16T22:30:45.99+01:00') == 869088646
    assert iso8601ts_to_timestamp('1997-07-16T22:30:45.999+01:00') == 869088646
    assert iso8601ts_to_timestamp('1997-07-16T21:30:45+00:00') == 869088645


def test_invert_pair():
    assert invert_pair('BTC_ETH') == 'ETH_BTC'
    assert invert_pair('XMR_EUR') == 'EUR_XMR'
    with pytest.raises(UnprocessableTradePair):
        assert invert_pair('sdsadasd')


def test_combine_dicts():
    a = {'a': 1, 'b': 2, 'c': 3}
    b = {'a': 4, 'c': 2}
    result = combine_dicts(a, b)
    assert result == {'a': 5, 'b': 2, 'c': 5}


def test_combine_stat_dicts():
    a = {
        'EUR': {'amount': FVal('50.5'), 'usd_value': FVal('200.1')},
        'BTC': {'amount': FVal('2.5'), 'usd_value': FVal('12200.5')},
    }
    b = {
        'RDN': {'amount': FVal('15.5'), 'usd_value': FVal('105.9')},
    }
    c = {
        'EUR': {'amount': FVal('15.5'), 'usd_value': FVal('105.9')},
        'BTC': {'amount': FVal('3.5'), 'usd_value': FVal('18200.5')},
        'ETH': {'amount': FVal('100.1'), 'usd_value': FVal('11200.1')},
    }
    result = combine_stat_dicts([a, b, c])
    assert result == {
        'EUR': {'amount': FVal('66'), 'usd_value': FVal('306')},
        'RDN': {'amount': FVal('15.5'), 'usd_value': FVal('105.9')},
        'ETH': {'amount': FVal('100.1'), 'usd_value': FVal('11200.1')},
        'BTC': {'amount': FVal('6'), 'usd_value': FVal('30401')},
    }


def test_check_if_version_up_to_date():
    def mock_github_return_current(url):  # pylint: disable=unused-argument
        contents = '{"tag_name": "v1.4.0", "html_url": "https://foo"}'
        return MockResponse(200, contents)
    patch_github = patch('requests.get', side_effect=mock_github_return_current)

    def mock_system_spec():
        return {'rotkehlchen': 'v1.4.0'}
    patch_our_version = patch(
        'rotkehlchen.utils.version_check.get_system_spec',
        side_effect=mock_system_spec,
    )

    with patch_our_version, patch_github:
        result = check_if_version_up_to_date()
        assert result.download_url is None, 'Same version should return None as url'

    def mock_github_return(url):  # pylint: disable=unused-argument
        contents = '{"tag_name": "v99.99.99", "html_url": "https://foo"}'
        return MockResponse(200, contents)

    with patch('requests.get', side_effect=mock_github_return):
        result = check_if_version_up_to_date()
    assert result
    assert result[0]
    assert result.latest_version == 'v99.99.99'
    assert result.download_url == 'https://foo'

    # Also test that bad responses are handled gracefully
    def mock_non_200_github_return(url):  # pylint: disable=unused-argument
        contents = '{"tag_name": "v99.99.99", "html_url": "https://foo"}'
        return MockResponse(501, contents)

    with patch('requests.get', side_effect=mock_non_200_github_return):
        result = check_if_version_up_to_date()
        assert result.our_version
        assert not result.latest_version
        assert not result.latest_version

    def mock_missing_fields_github_return(url):  # pylint: disable=unused-argument
        contents = '{"html_url": "https://foo"}'
        return MockResponse(200, contents)

    with patch('requests.get', side_effect=mock_missing_fields_github_return):
        result = check_if_version_up_to_date()
        assert result.our_version
        assert not result.latest_version
        assert not result.latest_version

    def mock_invalid_json_github_return(url):  # pylint: disable=unused-argument
        contents = '{html_url: "https://foo"}'
        return MockResponse(200, contents)

    with patch('requests.get', side_effect=mock_invalid_json_github_return):
        result = check_if_version_up_to_date()
        assert result.our_version
        assert not result.latest_version
        assert not result.latest_version


class Foo(CacheableObject):
    def __init__(self):
        super().__init__()

        self.do_sum_call_count = 0
        self.do_something_call_count = 0

    @cache_response_timewise()
    def do_sum(self, arg1, arg2, **kwargs):  # pylint: disable=no-self-use, unused-argument
        self.do_sum_call_count += 1
        return arg1 + arg2

    @cache_response_timewise()
    def do_something(self, **kwargs):  # pylint: disable=unused-argument
        self.do_something_call_count += 1
        return 5


def test_cache_response_timewise():
    """Test that cached value is called and not the function again"""
    instance = Foo()

    assert instance.do_something() == 5
    assert instance.do_something() == 5

    assert instance.do_something_call_count == 1


def test_cache_response_timewise_different_args():
    """Test that applying the cache timewise decorator works fine for different arguments

    Regression test for https://github.com/rotki/rotki/issues/543
    """
    instance = Foo()
    assert instance.do_sum(1, 1) == 2
    assert instance.do_sum(2, 2) == 4
    assert instance.do_sum_call_count == 2


def test_cache_response_timewise_ignore_cache():
    """Test that if the magic keyword argument `ignore_cache=True` is given the cache is ignored"""
    instance = Foo()

    assert instance.do_something() == 5
    assert instance.do_something(ignore_cache=True) == 5
    assert instance.do_something_call_count == 2

    assert instance.do_sum(1, 1) == 2
    assert instance.do_sum(1, 1) == 2
    assert instance.do_sum(1, 1, ignore_cache=True) == 2
    assert instance.do_sum_call_count == 2


def test_convert_to_int():
    assert convert_to_int('5') == 5
    with pytest.raises(ConversionError):
        assert convert_to_int(5.44, accept_only_exact=True) == 5
    assert convert_to_int(5.44, accept_only_exact=False) == 5
    assert convert_to_int(5.65, accept_only_exact=False) == 5
    with pytest.raises(ConversionError):
        assert convert_to_int(FVal('5.44'), accept_only_exact=True) == 5
    assert convert_to_int(FVal('5.44'), accept_only_exact=False) == 5
    assert convert_to_int(FVal('5.65'), accept_only_exact=False) == 5
    assert convert_to_int(FVal('4'), accept_only_exact=True) == 4
    assert convert_to_int(3) == 3
    with pytest.raises(ConversionError):
        assert convert_to_int('5.44', accept_only_exact=True) == 5
    assert convert_to_int('5.44', accept_only_exact=False) == 5
    assert convert_to_int('5.65', accept_only_exact=False) == 5
    assert convert_to_int('4', accept_only_exact=False) == 4
    with pytest.raises(ConversionError):
        assert convert_to_int(b'5.44', accept_only_exact=True) == 5
    assert convert_to_int(b'5.44', accept_only_exact=False) == 5
    assert convert_to_int(b'5.65', accept_only_exact=False) == 5
    assert convert_to_int(b'4', accept_only_exact=False) == 4
