"""Utility functions."""


import argparse
import copy
import importlib
import logging
import os
import textwrap

import yaml

import cloudmarker
from cloudmarker import baseconfig

_log = logging.getLogger(__name__)


def load_config(config_paths):
    """Load configuration from specified configuration paths.

    Arguments:
        config_paths (list): Configuration paths.

    Returns:
        dict: A dictionary of configuration key-value pairs.

    """
    config = baseconfig.config_dict

    for config_path in config_paths:
        config_path = os.path.expanduser(config_path)
        _log.info('Looking for %s', config_path)

        if not os.path.isfile(config_path):
            continue

        _log.info('Found %s', config_path)
        with open(config_path) as f:
            new_config = yaml.safe_load(f)
            config = merge_dicts(config, new_config)

    return config


def load_plugin(plugin_config):
    """Construct an object with specified plugin class and parameters.

    The ``plugin_config`` parameter must be a dictionary with the
    following keys:

    - ``plugin``: The value for this key must be a string that
      represents the fully qualified class name of the plugin. The
      fully qualified class name is in the dotted notation, e.g.,
      ``pkg.module.ClassName``.
    - ``params``: The value for this key must be a :obj:`dict` that
      represents the parameters to be passed to the ``__init__`` method
      of the plugin class. Each key in the dictionary represents the
      parameter name and each value represents the value of the
      parameter.

    Example:
        Here is an example usage of this function:

        >>> from cloudmarker import util
        >>> plugin_config = {
        ...     'plugin': 'cloudmarker.clouds.mockcloud.MockCloud',
        ...     'params': {
        ...         'record_count': 4,
        ...         'record_types': ('baz', 'qux')
        ...     }
        ... }
        ...
        >>> plugin = util.load_plugin(plugin_config)
        >>> print(type(plugin))
        <class 'cloudmarker.clouds.mockcloud.MockCloud'>
        >>> for record in plugin.read():
        ...     print(record['raw']['data'],
        ...           record['ext']['type'],
        ...           record['com']['type'])
        ...
        0 baz mock
        1 qux mock
        2 baz mock
        3 qux mock

    Arguments:
        plugin_config (dict): Plugin configuration dictionary.

    Returns:
        object: An object of type mentioned in the ``plugin`` parameter.

    Raises:
        PluginError: If plugin class name is invalid.

    """
    # Split the fully qualified class name into module and class names.
    parts = plugin_config['plugin'].rsplit('.', 1)

    # Validate that the fully qualified class name had at least two
    # parts: module name and class name.
    if len(parts) < 2:
        msg = ('Invalid plugin class name: {}; expected format: '
               '[<pkg>.]<module>.<class>'.format(plugin_config['plugin']))
        raise PluginError(msg)

    # Load the specified adapter class from the specified module.
    plugin_module = importlib.import_module(parts[0])
    plugin_class = getattr(plugin_module, parts[1])

    # Initialize params to empty dictionary if none was specified.
    plugin_params = plugin_config.get('params', {})

    # Construct the plugin.
    plugin = plugin_class(**plugin_params)
    return plugin


def parse_cli(args=None):
    """Parse command line arguments.

    Arguments:
        args (list): List of command line arguments.

    Returns:
        argparse.Namespace: Parsed command line arguments.

    """
    default_config_paths = [
        '/etc/cloudmarker.yaml',
        '~/.cloudmarker.yaml',
        '~/cloudmarker.yaml',
        'cloudmarker.yaml',
    ]

    description = """
    Audit clouds as specified by configuration.

    Zero or more config files are specified with the -c/--config option.
    The config files specified are merged with a built-in base config.
    Use the -p/--print-base-config option to see the built-in base
    config. Missing config files are ignored.

    If two or more config files provide conflicting config values, the
    config file specified later overrides the built-in base config and
    the config files specified earlier.

    If the -c/--config option is specified without any file arguments
    following it, then only the built-in base config is used.

    If the -c/--config option is omitted, then the following config
    files are searched for and merged with the built-in base config: {}.
    Missing config files are ignored.
    """
    description = description.format(friendly_list(default_config_paths))
    description = wrap_paragraphs(description)

    # We will use this format to preserve formatting of the description
    # above with the newlines and blank lines intact. The default
    # formatter line-wraps the entire description after ignoring any
    # superfluous whitespace including blank lines, so the paragraph
    # breaks are lost, and the usage description looks ugly.
    formatter = argparse.RawDescriptionHelpFormatter

    parser = argparse.ArgumentParser(prog='cloudmarker',
                                     description=description,
                                     formatter_class=formatter)

    parser.add_argument('-c', '--config', nargs='*',
                        default=default_config_paths,
                        help='run audits with specified configuration files')

    parser.add_argument('-n', '--now', action='store_true',
                        help='ignore configured schedule and run audits now')

    parser.add_argument('-p', '--print-base-config', action='store_true',
                        help='print base configuration')

    parser.add_argument('-v', '--version', action='version',
                        version='%(prog)s ' + cloudmarker.__version__)

    args = parser.parse_args(args)
    return args


def wrap_paragraphs(text, width=70):
    """Wrap each paragraph in ``text`` to the specified ``width``.

    If the ``text`` is indented with any common leading whitespace, then
    that common leading whitespace is removed from every line in text.
    Further, any remaining leading and trailing whitespace is removed.
    Finally, each paragraph is wrapped to the specified ``width``.

    Arguments:
        width (int): Maximum length of wrapped lines.
    """
    # Remove any common leading indentation from all lines.
    text = textwrap.dedent(text).strip()

    # Split the text into paragraphs.
    paragraphs = text.split('\n\n')

    # Wrap each paragraph and join them back into a single string.
    wrapped = '\n\n'.join(textwrap.fill(p, width) for p in paragraphs)
    return wrapped


def merge_dicts(a, b):
    """Recursively merge two dictionaries.

    The input dictionaries are not modified. A deepcopy of ``a`` is
    created and then ``b`` is merged into it.

    Example:
        Here is an example usage of this function:

        >>> from cloudmarker import util
        >>> a = {'a': 'apple', 'b': 'ball'}
        >>> b = {'b': 'bat', 'c': 'cat'}
        >>> c = util.merge_dicts(a, b)
        >>> print(c == {'a': 'apple', 'b': 'bat', 'c': 'cat'})
        True

    Arguments:
        a (dict): First dictionary.
        b (dict): Second dictionary.

    Returns:
        dict: Merged dictionary.

    """
    c = copy.deepcopy(a)
    for k in b:
        if (k in a and isinstance(a[k], dict) and isinstance(b[k], dict)):
            c[k] = merge_dicts(a[k], b[k])
        else:
            c[k] = copy.deepcopy(b[k])
    return c


def expand_port_ranges(port_ranges):
    """Expand ``port_ranges`` to a :obj:`set` of ports.

    Examples:
        Here is an example usage of this function:

        >>> from cloudmarker import util
        >>> ports = util.expand_port_ranges(['22', '3389', '8080-8085'])
        >>> print(ports == {22, 3389, 8080, 8081, 8082, 8083, 8084, 8085})
        True
        >>> ports = util.expand_port_ranges(['8080-8084', '8082-8086'])
        >>> print(ports == {8080, 8081, 8082, 8083, 8084, 8085, 8086})
        True

        Note that in a port range of the form ``m-n``, both ``m`` and
        ``n`` are included in the expanded port set. If ``m > n``, we
        get an empty port set.

        >>> ports = util.expand_port_ranges(['8085-8080'])
        >>> print(ports == set())
        True

        If the port range is invalid, :class:`PortRangeError` is raised.

        >>> util.expand_port_ranges(['8080a'])
        Traceback (most recent call last):
            ...
        cloudmarker.util.PortRangeError: Invalid port range: 8080a
        >>> util.expand_port_ranges(['8080a-8085'])
        Traceback (most recent call last):
            ...
        cloudmarker.util.PortRangeError: Invalid port in port range: 8080a-8085

    Arguments:
        port_ranges (list): A list of strings where each string is a
            port number (e.g., ``'80'``) or port range (e.g., ``80-89``).

    Returns:
        set: A set of integers that represent the ports specified
            by ``port_ranges``.

    """
    # The return value is a set of ports, so that every port number
    # occurs only once even if they are found multiple times in
    # overlapping port ranges, e.g., ['8080-8084', '8082-8086'].
    expanded_port_set = set()

    for port_range in port_ranges:
        # If it's just a port number, e.g., '80', add it to the result set.
        if port_range.isdigit():
            expanded_port_set.add(int(port_range))
            continue

        # Otherwise, it must look like a port range, e.g., '1024-9999'.
        if '-' not in port_range:
            raise PortRangeError('Invalid port range: {}'
                                 .format(port_range))

        # If it looks like a port range, it must be two numbers
        # with a hyphen between them.
        start_port, end_port = port_range.split('-', 1)
        if not start_port.isdigit() or not end_port.isdigit():
            raise PortRangeError('Invalid port in port range: {}'
                                 .format(port_range))

        # Add the port numbers in the port range to the result set.
        expanded_ports = range(int(start_port), int(end_port) + 1)
        expanded_port_set.update(expanded_ports)

    return expanded_port_set


def friendly_string(technical_string):
    """Translate a technical string to a human-friendly phrase.

    In most of our code, we use succint strings to express various
    technical details, e.g., ``'gcp'`` to express Google Cloud Platform.
    However these technical strings are not ideal while writing
    human-friendly messages such as a description of a security issue
    detected or a recommendation to remediate such an issue.

    This function helps in converting such technical strings into
    human-friendly phrases that can be used in strings intended to be
    read by end users (e.g., security analysts responsible for
    protecting their cloud infrastructure) of this project.

    Examples:
        Here are a few example usages of this function:

        >>> from cloudmarker import util
        >>> util.friendly_string('azure')
        'Azure'
        >>> util.friendly_string('gcp')
        'Google Cloud Platform (GCP)'

    Arguments:
        technical_string (str): A technical string.

    Returns:
        str: Human-friendly string if a translation from a technical
            string to friendly string exists; the same string otherwise.

    """
    phrase_map = {
        'azure': 'Azure',
        'gcp': 'Google Cloud Platform (GCP)'
    }
    return phrase_map.get(technical_string, technical_string)


def friendly_list(items, conjunction='and'):
    """Translate a list of items to a human-friendly list of items.

    Examples:
        Here are a few example usages of this function:

        >>> from cloudmarker import util
        >>> util.friendly_list([])
        'none'
        >>> util.friendly_list(['apple'])
        'apple'
        >>> util.friendly_list(['apple', 'ball'])
        'apple and ball'
        >>> util.friendly_list(['apple', 'ball', 'cat'])
        'apple, ball, and cat'
        >>> util.friendly_list(['apple', 'ball'], 'or')
        'apple or ball'
        >>> util.friendly_list(['apple', 'ball', 'cat'], 'or')
        'apple, ball, or cat'

    Arguments:
        items (list): List of items.

    Returns:
        str: Human-friendly list of items with correct placement of
            comma and conjunction.

    """
    if not items:
        return 'none'

    items = [str(item) for item in items]

    if len(items) == 1:
        return items[0]

    if len(items) == 2:
        return items[0] + ' ' + conjunction + ' ' + items[1]

    return ', '.join(items[:-1]) + ', ' + conjunction + ' ' + items[-1]


def pluralize(count, word, *suffixes):
    """Convert ``word`` to plural form if ``count`` is not ``1``.

    Examples:
        In the simplest form usage, this function just adds an ``'s'``
        to the input word when the plural form needs to be used.

        >>> from cloudmarker import util
        >>> util.pluralize(0, 'apple')
        'apples'
        >>> util.pluralize(1, 'apple')
        'apple'
        >>> util.pluralize(2, 'apple')
        'apples'

        The plural form of some words cannot be formed merely by adding
        an ``'s'`` to the word but requires adding a different suffix.
        For such cases, provide an additional argument that specifies
        the correct suffix.

        >>> util.pluralize(0, 'potato', 'es')
        'potatoes'
        >>> util.pluralize(1, 'potato', 'es')
        'potato'
        >>> util.pluralize(2, 'potato', 'es')
        'potatoes'

        The plural form of some words cannot be formed merely by adding
        a suffix but requires removing a suffix and then adding a new
        suffix. For such cases, provide two additional arguments: one
        that specifies the suffix to remove from the input word and
        another to specify the suffix to add.

        >>> util.pluralize(0, 'sky', 'y', 'ies')
        'skies'
        >>> util.pluralize(1, 'sky', 'y', 'ies')
        'sky'
        >>> util.pluralize(2, 'sky', 'y', 'ies')
        'skies'

    Returns:
        str: The input ``word`` itself if ``count`` is ``1``; plural
            form of the ``word`` otherwise.

    """
    if not suffixes:
        remove, append = '', 's'
    elif len(suffixes) == 1:
        remove, append = '', suffixes[0]
    elif len(suffixes) == 2:
        remove, append = suffixes[0], suffixes[1]
    else:
        raise PluralizeError('Surplus argument: {!r}'.format(suffixes[2]))

    if count == 1:
        return word

    if remove != '' and word.endswith(remove):
        word = word[:-len(remove)]
    word = word.rstrip(remove)
    return word + append


class PluginError(Exception):
    """Represents an error while loading a plugin."""


class PortRangeError(Exception):
    """Represents an error in parsing a port range."""


class PluralizeError(Exception):
    """Represents an error while converting a word to plural form."""
