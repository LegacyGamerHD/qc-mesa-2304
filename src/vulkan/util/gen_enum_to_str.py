# Copyright © 2017 Intel Corporation

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Create enum to string functions for vulkan using vk.xml."""

import argparse
import functools
import os
import re
import textwrap
import xml.etree.ElementTree as et

from mako.template import Template

COPYRIGHT = textwrap.dedent(u"""\
    * Copyright © 2017 Intel Corporation
    *
    * Permission is hereby granted, free of charge, to any person obtaining a copy
    * of this software and associated documentation files (the "Software"), to deal
    * in the Software without restriction, including without limitation the rights
    * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    * copies of the Software, and to permit persons to whom the Software is
    * furnished to do so, subject to the following conditions:
    *
    * The above copyright notice and this permission notice shall be included in
    * all copies or substantial portions of the Software.
    *
    * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    * SOFTWARE.""")

C_TEMPLATE = Template(textwrap.dedent(u"""\
    /* Autogenerated file -- do not edit
     * generated by ${file}
     *
     ${copyright}
     */

    #include <string.h>
    #include <vulkan/vulkan.h>
    #include <vulkan/vk_android_native_buffer.h>
    #include <vulkan/vk_layer.h>
    #include "util/macros.h"
    #include "vk_enum_to_str.h"

    % for enum in enums:

      % if enum.guard:
#ifdef ${enum.guard}
      % endif
    const char *
    vk_${enum.name[2:]}_to_str(${enum.name} input)
    {
        switch((int64_t)input) {
    % for v in sorted(enum.values.keys()):
        case ${v}:
            return "${enum.values[v]}";
    % endfor
        case ${enum.max_enum_name}: return "${enum.max_enum_name}";
        default:
            return "Unknown ${enum.name} value.";
        }
    }

      % if enum.guard:
#endif
      % endif
    %endfor

    size_t vk_structure_type_size(const struct VkBaseInStructure *item)
    {
        switch((int)item->sType) {
    % for struct in structs:
        % if struct.extension is not None and struct.extension.define is not None:
    #ifdef ${struct.extension.define}
        case ${struct.stype}: return sizeof(${struct.name});
    #endif
        % else:
        case ${struct.stype}: return sizeof(${struct.name});
        % endif
    %endfor
        case VK_STRUCTURE_TYPE_LOADER_INSTANCE_CREATE_INFO: return sizeof(VkLayerInstanceCreateInfo);
        case VK_STRUCTURE_TYPE_LOADER_DEVICE_CREATE_INFO: return sizeof(VkLayerDeviceCreateInfo);
        default:
            unreachable("Undefined struct type.");
        }
    }

    const char *
    vk_ObjectType_to_ObjectName(VkObjectType type)
    {
        switch((int)type) {
    % for object_type in sorted(object_types[0].enum_to_name.keys()):
        case ${object_type}:
            return "${object_types[0].enum_to_name[object_type]}";
    % endfor
        default:
            return "Unknown VkObjectType value.";
        }
    }
    """))

H_TEMPLATE = Template(textwrap.dedent(u"""\
    /* Autogenerated file -- do not edit
     * generated by ${file}
     *
     ${copyright}
     */

    #ifndef MESA_VK_ENUM_TO_STR_H
    #define MESA_VK_ENUM_TO_STR_H

    #include <vulkan/vulkan.h>
    #include <vulkan/vk_android_native_buffer.h>

    #ifdef __cplusplus
    extern "C" {
    #endif

    % for enum in enums:
      % if enum.guard:
#ifdef ${enum.guard}
      % endif
    const char * vk_${enum.name[2:]}_to_str(${enum.name} input);
      % if enum.guard:
#endif
      % endif
    % endfor

    size_t vk_structure_type_size(const struct VkBaseInStructure *item);

    const char * vk_ObjectType_to_ObjectName(VkObjectType type);

    #ifdef __cplusplus
    } /* extern "C" */
    #endif

    #endif"""))


H_DEFINE_TEMPLATE = Template(textwrap.dedent(u"""\
    /* Autogenerated file -- do not edit
     * generated by ${file}
     *
     ${copyright}
     */

    #ifndef MESA_VK_ENUM_DEFINES_H
    #define MESA_VK_ENUM_DEFINES_H

    #include <vulkan/vulkan.h>
    #include <vulkan/vk_android_native_buffer.h>

    #ifdef __cplusplus
    extern "C" {
    #endif

    % for ext in extensions:
    #define _${ext.name}_number (${ext.number})
    % endfor

    % for enum in bitmasks:
      % if enum.bitwidth > 32:
        <% continue %>
      % endif
      % if enum.guard:
#ifdef ${enum.guard}
      % endif
    #define ${enum.all_bits_name()} ${hex(enum.all_bits_value())}u
      % if enum.guard:
#endif
      % endif
    % endfor

    % for enum in bitmasks:
      % if enum.bitwidth < 64:
        <% continue %>
      % endif
    /* Redefine bitmask values of ${enum.name} */
      % if enum.guard:
#ifdef ${enum.guard}
      % endif
      % for n, v in enum.name_to_value.items():
    #define ${n} (${hex(v)}ULL)
      % endfor
      % if enum.guard:
#endif
      % endif
    % endfor

    static inline VkFormatFeatureFlags
    vk_format_features2_to_features(VkFormatFeatureFlags2 features2)
    {
       return features2 & VK_ALL_FORMAT_FEATURE_FLAG_BITS;
    }

    #ifdef __cplusplus
    } /* extern "C" */
    #endif

    #endif"""))


class NamedFactory(object):
    """Factory for creating enums."""

    def __init__(self, type_):
        self.registry = {}
        self.type = type_

    def __call__(self, name, **kwargs):
        try:
            return self.registry[name]
        except KeyError:
            n = self.registry[name] = self.type(name, **kwargs)
        return n

    def get(self, name):
        return self.registry.get(name)


class VkExtension(object):
    """Simple struct-like class representing extensions"""

    def __init__(self, name, number=None, define=None):
        self.name = name
        self.number = number
        self.define = define


def CamelCase_to_SHOUT_CASE(s):
   return (s[:1] + re.sub(r'(?<![A-Z])([A-Z])', r'_\1', s[1:])).upper()

def compute_max_enum_name(s):
    max_enum_name = CamelCase_to_SHOUT_CASE(s)
    last_prefix = max_enum_name.rsplit('_', 1)[-1]
    # Those special prefixes need to be always at the end
    if last_prefix in ['AMD', 'EXT', 'INTEL', 'KHR', 'NV', 'LUNARG'] :
        max_enum_name = "_".join(max_enum_name.split('_')[:-1])
        max_enum_name = max_enum_name + "_MAX_ENUM_" + last_prefix
    else:
        max_enum_name = max_enum_name + "_MAX_ENUM"

    return max_enum_name

class VkEnum(object):
    """Simple struct-like class representing a single Vulkan Enum."""

    def __init__(self, name, bitwidth=32, values=None):
        self.name = name
        self.max_enum_name = compute_max_enum_name(name)
        self.bitwidth = bitwidth
        self.extension = None
        # Maps numbers to names
        self.values = values or dict()
        self.name_to_value = dict()
        self.guard = None
        self.name_to_alias_list = {}

    def all_bits_name(self):
        assert self.name.startswith('Vk')
        assert re.search(r'FlagBits[A-Z]*$', self.name)

        return 'VK_ALL_' + CamelCase_to_SHOUT_CASE(self.name[2:])

    def all_bits_value(self):
        return functools.reduce(lambda a,b: a | b, self.values.keys(), 0)

    def add_value(self, name, value=None,
                  extnum=None, offset=None, alias=None,
                  error=False):
        if alias is not None:
            assert value is None and offset is None
            if alias not in self.name_to_value:
                # We don't have this alias yet.  Just record the alias and
                # we'll deal with it later.
                alias_list = self.name_to_alias_list.setdefault(alias, [])
                alias_list.append(name);
                return

            # Use the value from the alias
            value = self.name_to_value[alias]

        assert value is not None or extnum is not None
        if value is None:
            value = 1000000000 + (extnum - 1) * 1000 + offset
            if error:
                value = -value

        self.name_to_value[name] = value
        if value not in self.values:
            self.values[value] = name
        elif len(self.values[value]) > len(name):
            self.values[value] = name

        # Now that the value has been fully added, resolve aliases, if any.
        if name in self.name_to_alias_list:
            for alias in self.name_to_alias_list[name]:
                self.add_value(alias, value)
            del self.name_to_alias_list[name]

    def add_value_from_xml(self, elem, extension=None):
        self.extension = extension
        if 'value' in elem.attrib:
            self.add_value(elem.attrib['name'],
                           value=int(elem.attrib['value'], base=0))
        elif 'bitpos' in elem.attrib:
            self.add_value(elem.attrib['name'],
                           value=(1 << int(elem.attrib['bitpos'], base=0)))
        elif 'alias' in elem.attrib:
            self.add_value(elem.attrib['name'], alias=elem.attrib['alias'])
        else:
            error = 'dir' in elem.attrib and elem.attrib['dir'] == '-'
            if 'extnumber' in elem.attrib:
                extnum = int(elem.attrib['extnumber'])
            else:
                extnum = extension.number
            self.add_value(elem.attrib['name'],
                           extnum=extnum,
                           offset=int(elem.attrib['offset']),
                           error=error)

    def set_guard(self, g):
        self.guard = g


class VkChainStruct(object):
    """Simple struct-like class representing a single Vulkan struct identified with a VkStructureType"""
    def __init__(self, name, stype):
        self.name = name
        self.stype = stype
        self.extension = None


def struct_get_stype(xml_node):
    for member in xml_node.findall('./member'):
        name = member.findall('./name')
        if len(name) > 0 and name[0].text == "sType":
            return member.get('values')
    return None

class VkObjectType(object):
    """Simple struct-like class representing a single Vulkan object type"""
    def __init__(self, name):
        self.name = name
        self.enum_to_name = dict()


def parse_xml(enum_factory, ext_factory, struct_factory, bitmask_factory,
              obj_type_factory, filename):
    """Parse the XML file. Accumulate results into the factories.

    This parser is a memory efficient iterative XML parser that returns a list
    of VkEnum objects.
    """

    xml = et.parse(filename)

    for enum_type in xml.findall('./enums[@type="enum"]'):
        enum = enum_factory(enum_type.attrib['name'])
        for value in enum_type.findall('./enum'):
            enum.add_value_from_xml(value)

    # For bitmask we only add the Enum selected for convenience.
    for enum_type in xml.findall('./enums[@type="bitmask"]'):
        bitwidth = int(enum_type.attrib.get('bitwidth', 32))
        enum = bitmask_factory(enum_type.attrib['name'], bitwidth=bitwidth)
        for value in enum_type.findall('./enum'):
            enum.add_value_from_xml(value)

    for value in xml.findall('./feature/require/enum[@extends]'):
        extends = value.attrib['extends']
        enum = enum_factory.get(extends)
        if enum is not None:
            enum.add_value_from_xml(value)
        enum = bitmask_factory.get(extends)
        if enum is not None:
            enum.add_value_from_xml(value)

    for struct_type in xml.findall('./types/type[@category="struct"]'):
        name = struct_type.attrib['name']
        stype = struct_get_stype(struct_type)
        if stype is not None:
            struct_factory(name, stype=stype)

    platform_define = {}
    for platform in xml.findall('./platforms/platform'):
        name = platform.attrib['name']
        define = platform.attrib['protect']
        platform_define[name] = define

    for ext_elem in xml.findall('./extensions/extension[@supported="vulkan"]'):
        define = None
        if "platform" in ext_elem.attrib:
            define = platform_define[ext_elem.attrib['platform']]
        extension = ext_factory(ext_elem.attrib['name'],
                                number=int(ext_elem.attrib['number']),
                                define=define)

        for value in ext_elem.findall('./require/enum[@extends]'):
            extends = value.attrib['extends']
            enum = enum_factory.get(extends)
            if enum is not None:
                enum.add_value_from_xml(value, extension)
            enum = bitmask_factory.get(extends)
            if enum is not None:
                enum.add_value_from_xml(value, extension)
        for t in ext_elem.findall('./require/type'):
            struct = struct_factory.get(t.attrib['name'])
            if struct is not None:
                struct.extension = extension

        if define:
            for value in ext_elem.findall('./require/type[@name]'):
                enum = enum_factory.get(value.attrib['name'])
                if enum is not None:
                    enum.set_guard(define)

    obj_types = obj_type_factory("VkObjectType")
    for object_type in xml.findall('./types/type[@category="handle"]'):
        for object_name in object_type.findall('./name'):
            # Convert to int to avoid undefined enums
            enum = object_type.attrib['objtypeenum']
            enum_val = enum_factory.get("VkObjectType").name_to_value[enum]
            obj_types.enum_to_name[enum_val] = object_name.text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--xml', required=True,
                        help='Vulkan API XML files',
                        action='append',
                        dest='xml_files')
    parser.add_argument('--outdir',
                        help='Directory to put the generated files in',
                        required=True)

    args = parser.parse_args()

    enum_factory = NamedFactory(VkEnum)
    ext_factory = NamedFactory(VkExtension)
    struct_factory = NamedFactory(VkChainStruct)
    obj_type_factory = NamedFactory(VkObjectType)
    bitmask_factory = NamedFactory(VkEnum)

    for filename in args.xml_files:
        parse_xml(enum_factory, ext_factory, struct_factory, bitmask_factory,
                  obj_type_factory, filename)
    enums = sorted(enum_factory.registry.values(), key=lambda e: e.name)
    extensions = sorted(ext_factory.registry.values(), key=lambda e: e.name)
    structs = sorted(struct_factory.registry.values(), key=lambda e: e.name)
    bitmasks = sorted(bitmask_factory.registry.values(), key=lambda e: e.name)
    object_types = sorted(obj_type_factory.registry.values(), key=lambda e: e.name)

    for template, file_ in [(C_TEMPLATE, os.path.join(args.outdir, 'vk_enum_to_str.c')),
                            (H_TEMPLATE, os.path.join(args.outdir, 'vk_enum_to_str.h')),
                            (H_DEFINE_TEMPLATE, os.path.join(args.outdir, 'vk_enum_defines.h'))]:
        with open(file_, 'w', encoding='utf-8') as f:
            f.write(template.render(
                file=os.path.basename(__file__),
                enums=enums,
                extensions=extensions,
                structs=structs,
                bitmasks=bitmasks,
                object_types=object_types,
                copyright=COPYRIGHT))


if __name__ == '__main__':
    main()
