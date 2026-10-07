#!/usr/bin/env python3
"""Generate the mainline SM7250 TLMM driver + binding from downstream data.

Sources:
  - downstream drivers/pinctrl/qcom/pinctrl-lito.c (pins, mux tables, SDC/UFS)
  - live device tree (tlmm irqdomain-map) for the GPIO -> PDC wakeup map

Conversions to mainline conventions:
  - tiled layout: south/west/east register regions, ctl_reg relative to tile
  - NA -> "_" (no function), names lower-cased
  - numbered debug functions merged (phase_flagN -> phase_flag, qdss_gpioN ->
    qdss_gpio, atest_usbNN -> atest_usb, atest_charN -> atest_char)
"""
import re
import sys

DOWN = sys.argv[1]          # pinctrl-lito.c
LIVE = sys.argv[2]          # lineage-live.dts
OUT_C = sys.argv[3]
OUT_YAML = sys.argv[4]

src = open(DOWN).read()
TILE_BASE = {'SOUTH': 0x100000, 'WEST': 0x500000, 'EAST': 0x900000}
TILES = ['south', 'west', 'east']           # reg-names / tile index order

def fname(f):
    f = f.strip()
    if f == 'NA':
        return '_'
    f = f.lower()
    for pat, rep in ((r'^phase_flag\d+$', 'phase_flag'), (r'^qdss_gpio\d+$', 'qdss_gpio'),
                     (r'^atest_usb\d+$', 'atest_usb'), (r'^atest_char\d+$', 'atest_char')):
        f = re.sub(pat, rep, f)
    return f

# --- pins ---------------------------------------------------------------
pins = [(int(n), name) for n, name in re.findall(r'PINCTRL_PIN\((\d+), "([A-Z0-9_]+)"\)', src)]
assert [n for n, _ in pins] == list(range(len(pins))), 'pin numbering gap'
NGPIOS = int(re.search(r'\.ngpios = (\d+)', src).group(1))

# --- gpio groups --------------------------------------------------------
groups = {}
for m in re.finditer(r'\[(\d+)\] = PINGROUP\(([^)]*)\)', src):
    args = [a.strip() for a in m.group(2).replace('\n', ' ').split(',')]
    gid, tile, funcs = int(args[0]), args[1], args[2:11]
    assert int(m.group(1)) == gid and tile in TILE_BASE and len(funcs) == 9
    groups[gid] = (tile, [fname(f) for f in funcs])
assert sorted(groups) == list(range(NGPIOS))

special = []
for m in re.finditer(r'\[(\d+)\] = SDC_QDSD_PINGROUP\((\w+), (0x[0-9a-f]+), (\d+), (\d+)\)', src):
    special.append(('SDC', int(m.group(1)), m.group(2), int(m.group(3), 16), m.group(4), m.group(5)))
for m in re.finditer(r'\[(\d+)\] = UFS_RESET\((\w+), (0x[0-9a-f]+)\)', src):
    special.append(('UFS', int(m.group(1)), m.group(2), int(m.group(3), 16), None, None))

# Mainline convention (sm8250, sm8350, sc7280...): ufs_reset is the GPIO right
# after the last real one, so the UFS host can use it as reset-gpios; the SDC
# pads follow it.
special.sort(key=lambda sp: (sp[0] != 'UFS', sp[1]))
pin_name = dict(pins)
pins = pins[:NGPIOS] + [(NGPIOS + i, pin_name[sp[1]]) for i, sp in enumerate(special)]
special = [(sp[0], NGPIOS + i) + tuple(sp[2:]) for i, sp in enumerate(special)]
GPIO_LINES = NGPIOS + sum(sp[0] == 'UFS' for sp in special)

def tile_of(off):
    for t, b in TILE_BASE.items():
        if b <= off < b + 0x300000:
            return t, off - b
    raise ValueError(hex(off))

# --- functions ----------------------------------------------------------
func_groups = {}
for gid in range(NGPIOS):
    for f in groups[gid][1]:
        if f != '_':
            func_groups.setdefault(f, [])
            if f'gpio{gid}' not in func_groups[f]:
                func_groups[f].append(f'gpio{gid}')
functions = sorted(set(func_groups) | {'gpio'})

# --- wakeup map from live DT ----------------------------------------------
live = open(LIVE).read()
m = re.search(r'tlmm: pinctrl@f000000 \{.*?irqdomain-map = <([^>]*)>', live, re.S)
cells = [int(x, 16) for x in m.group(1).split()]
assert len(cells) % 5 == 0
wake = sorted((cells[i], cells[i + 3]) for i in range(0, len(cells), 5))

# --- emit C ---------------------------------------------------------------
o = []
w = o.append
w('''// SPDX-License-Identifier: GPL-2.0-only
/*
 * Copyright (c) 2018-2019, The Linux Foundation. All rights reserved.
 */

#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>

#include "pinctrl-msm.h"

static const char * const sm7250_tiles[] = {
\t"south",
\t"west",
\t"east",
};

enum {
\tSOUTH,
\tWEST,
\tEAST,
};

#define REG_SIZE 0x1000
#define PINGROUP(id, _tile, f1, f2, f3, f4, f5, f6, f7, f8, f9) \\
\t{\t\t\t\t\t\t\\
\t\t.grp = PINCTRL_PINGROUP("gpio" #id,\t\\
\t\t\tgpio##id##_pins,\t\t\\
\t\t\tARRAY_SIZE(gpio##id##_pins)),\t\\
\t\t.funcs = (int[]){\t\t\t\\
\t\t\tmsm_mux_gpio, /* gpio mode */\t\\
\t\t\tmsm_mux_##f1,\t\t\t\\
\t\t\tmsm_mux_##f2,\t\t\t\\
\t\t\tmsm_mux_##f3,\t\t\t\\
\t\t\tmsm_mux_##f4,\t\t\t\\
\t\t\tmsm_mux_##f5,\t\t\t\\
\t\t\tmsm_mux_##f6,\t\t\t\\
\t\t\tmsm_mux_##f7,\t\t\t\\
\t\t\tmsm_mux_##f8,\t\t\t\\
\t\t\tmsm_mux_##f9\t\t\t\\
\t\t},\t\t\t\t\t\\
\t\t.nfuncs = 10,\t\t\t\t\\
\t\t.ctl_reg = REG_SIZE * id,\t\t\\
\t\t.io_reg = REG_SIZE * id + 0x4,\t\t\\
\t\t.intr_cfg_reg = REG_SIZE * id + 0x8,\t\\
\t\t.intr_status_reg = REG_SIZE * id + 0xc,\t\\
\t\t.tile = _tile,\t\t\t\t\\
\t\t.mux_bit = 2,\t\t\t\t\\
\t\t.pull_bit = 0,\t\t\t\t\\
\t\t.drv_bit = 6,\t\t\t\t\\
\t\t.oe_bit = 9,\t\t\t\t\\
\t\t.in_bit = 0,\t\t\t\t\\
\t\t.out_bit = 1,\t\t\t\t\\
\t\t.intr_enable_bit = 0,\t\t\t\\
\t\t.intr_status_bit = 0,\t\t\t\\
\t\t.intr_target_bit = 5,\t\t\t\\
\t\t.intr_target_kpss_val = 3,\t\t\\
\t\t.intr_raw_status_bit = 4,\t\t\\
\t\t.intr_polarity_bit = 1,\t\t\t\\
\t\t.intr_detection_bit = 2,\t\t\\
\t\t.intr_detection_width = 2,\t\t\\
\t}

#define SDC_PINGROUP(pg_name, _tile, ctl, pull, drv)\t\\
\t{\t\t\t\t\t\t\\
\t\t.grp = PINCTRL_PINGROUP(#pg_name,\t\\
\t\t\tpg_name##_pins,\t\t\\
\t\t\tARRAY_SIZE(pg_name##_pins)),\t\\
\t\t.ctl_reg = ctl,\t\t\t\t\\
\t\t.io_reg = 0,\t\t\t\t\\
\t\t.intr_cfg_reg = 0,\t\t\t\\
\t\t.intr_status_reg = 0,\t\t\t\\
\t\t.tile = _tile,\t\t\t\t\\
\t\t.mux_bit = -1,\t\t\t\t\\
\t\t.pull_bit = pull,\t\t\t\\
\t\t.drv_bit = drv,\t\t\t\t\\
\t\t.oe_bit = -1,\t\t\t\t\\
\t\t.in_bit = -1,\t\t\t\t\\
\t\t.out_bit = -1,\t\t\t\t\\
\t\t.intr_enable_bit = -1,\t\t\t\\
\t\t.intr_status_bit = -1,\t\t\t\\
\t\t.intr_target_bit = -1,\t\t\t\\
\t\t.intr_raw_status_bit = -1,\t\t\\
\t\t.intr_polarity_bit = -1,\t\t\\
\t\t.intr_detection_bit = -1,\t\t\\
\t\t.intr_detection_width = -1,\t\t\\
\t}

#define UFS_RESET(pg_name, _tile, offset)\t\t\\
\t{\t\t\t\t\t\t\\
\t\t.grp = PINCTRL_PINGROUP(#pg_name,\t\\
\t\t\tpg_name##_pins,\t\t\\
\t\t\tARRAY_SIZE(pg_name##_pins)),\t\\
\t\t.ctl_reg = offset,\t\t\t\\
\t\t.io_reg = offset + 0x4,\t\t\t\\
\t\t.intr_cfg_reg = 0,\t\t\t\\
\t\t.intr_status_reg = 0,\t\t\t\\
\t\t.tile = _tile,\t\t\t\t\\
\t\t.mux_bit = -1,\t\t\t\t\\
\t\t.pull_bit = 3,\t\t\t\t\\
\t\t.drv_bit = 0,\t\t\t\t\\
\t\t.oe_bit = -1,\t\t\t\t\\
\t\t.in_bit = -1,\t\t\t\t\\
\t\t.out_bit = 0,\t\t\t\t\\
\t\t.intr_enable_bit = -1,\t\t\t\\
\t\t.intr_status_bit = -1,\t\t\t\\
\t\t.intr_target_bit = -1,\t\t\t\\
\t\t.intr_raw_status_bit = -1,\t\t\\
\t\t.intr_polarity_bit = -1,\t\t\\
\t\t.intr_detection_bit = -1,\t\t\\
\t\t.intr_detection_width = -1,\t\t\\
\t}
''')
w('static const struct pinctrl_pin_desc sm7250_pins[] = {')
for n, name in pins:
    w(f'\tPINCTRL_PIN({n}, "{name}"),')
w('};\n')
w('#define DECLARE_MSM_GPIO_PINS(pin) \\\n\tstatic const unsigned int gpio##pin##_pins[] = { pin }')
for g in range(NGPIOS):
    w(f'DECLARE_MSM_GPIO_PINS({g});')
w('')
for kind, idx, name, *_ in sorted(special, key=lambda s: s[1]):
    w(f'static const unsigned int {name}_pins[] = {{ {idx} }};')
w('\nenum sm7250_functions {')
for f in functions:
    w(f'\tmsm_mux_{f},')
w('\tmsm_mux__,\n};\n')
w('static const char * const gpio_groups[] = {')
line = '\t'
for g in range(NGPIOS):
    item = f'"gpio{g}", '
    if len(line.expandtabs()) + len(item) > 80:
        w(line.rstrip()); line = '\t'
    line += item
w(line.rstrip()); w('};\n')
for f in functions:
    if f == 'gpio':
        continue
    items = ', '.join(f'"{g}"' for g in func_groups[f])
    # wrap
    w(f'static const char * const {f}_groups[] = {{')
    line = '\t'
    for g in func_groups[f]:
        item = f'"{g}", '
        if len(line.expandtabs()) + len(item) > 80:
            w(line.rstrip()); line = '\t'
        line += item
    w(line.rstrip().rstrip(',') + ',')
    w('};\n')
w('static const struct pinfunction sm7250_functions[] = {')
for f in functions:
    w('\tMSM_GPIO_PIN_FUNCTION(gpio),' if f == 'gpio' else f'\tMSM_PIN_FUNCTION({f}),')
w('};\n')
w('/*\n * Every pin is maintained as a single group, and missing or non-existing pin\n'
  ' * would be maintained as dummy group to synchronize pin group index with\n'
  ' * pin descriptor registered with pinctrl core.\n'
  ' * Clients would not be able to request these dummy pin groups.\n */')
w('static const struct msm_pingroup sm7250_groups[] = {')
for g in range(NGPIOS):
    tile, fs = groups[g]
    w(f'\t[{g}] = PINGROUP({g}, {tile}, {", ".join(fs)}),')
for kind, idx, name, off, pull, drv in sorted(special, key=lambda s: s[1]):
    t, rel = tile_of(off)
    if kind == 'SDC':
        w(f'\t[{idx}] = SDC_PINGROUP({name}, {t}, {rel:#x}, {pull}, {drv}),')
    else:
        w(f'\t[{idx}] = UFS_RESET({name}, {t}, {rel:#x}),')
w('};\n')
w('static const struct msm_gpio_wakeirq_map sm7250_pdc_map[] = {')
line = '\t'
for gpio, pdc in wake:
    item = f'{{ {gpio}, {pdc} }}, '
    if len(line.expandtabs()) + len(item) > 80:
        w(line.rstrip()); line = '\t'
    line += item
w(line.rstrip()); w('};\n')
w(f'''static const struct msm_pinctrl_soc_data sm7250_tlmm = {{
\t.pins = sm7250_pins,
\t.npins = ARRAY_SIZE(sm7250_pins),
\t.functions = sm7250_functions,
\t.nfunctions = ARRAY_SIZE(sm7250_functions),
\t.groups = sm7250_groups,
\t.ngroups = ARRAY_SIZE(sm7250_groups),
\t.ngpios = {GPIO_LINES},
\t.tiles = sm7250_tiles,
\t.ntiles = ARRAY_SIZE(sm7250_tiles),
\t.wakeirq_map = sm7250_pdc_map,
\t.nwakeirq_map = ARRAY_SIZE(sm7250_pdc_map),
}};

static int sm7250_tlmm_probe(struct platform_device *pdev)
{{
\treturn msm_pinctrl_probe(pdev, &sm7250_tlmm);
}}

static const struct of_device_id sm7250_tlmm_of_match[] = {{
\t{{ .compatible = "qcom,sm7250-tlmm", }},
\t{{ }},
}};
MODULE_DEVICE_TABLE(of, sm7250_tlmm_of_match);

static struct platform_driver sm7250_tlmm_driver = {{
\t.driver = {{
\t\t.name = "sm7250-tlmm",
\t\t.of_match_table = sm7250_tlmm_of_match,
\t}},
\t.probe = sm7250_tlmm_probe,
}};

static int __init sm7250_tlmm_init(void)
{{
\treturn platform_driver_register(&sm7250_tlmm_driver);
}}
arch_initcall(sm7250_tlmm_init);

static void __exit sm7250_tlmm_exit(void)
{{
\tplatform_driver_unregister(&sm7250_tlmm_driver);
}}
module_exit(sm7250_tlmm_exit);

MODULE_DESCRIPTION("QTI SM7250 TLMM driver");
MODULE_LICENSE("GPL");''')
open(OUT_C, 'w').write('\n'.join(o) + '\n')

# --- emit binding -----------------------------------------------------------
specials = [s[2] for s in sorted(special, key=lambda s: s[1])]
def yaml_list(items, indent):
    lines, line = [], ' ' * indent + '['
    for i, it in enumerate(items):
        tok = it + (', ' if i < len(items) - 1 else ' ]')
        if len(line) + len(tok) > 80:
            lines.append(line.rstrip()); line = ' ' * (indent + 1)
        line += tok
    lines.append(line)
    return '\n'.join(lines)
last = NGPIOS - 1
gpio_pat = f'^gpio([0-9]|[1-9][0-9]|1[0-3][0-9]|14[0-{last % 10}])$'
assert last == 145
yaml = f'''# SPDX-License-Identifier: (GPL-2.0-only OR BSD-2-Clause)
%YAML 1.2
---
$id: http://devicetree.org/schemas/pinctrl/qcom,sm7250-tlmm.yaml#
$schema: http://devicetree.org/meta-schemas/core.yaml#

title: Qualcomm SM7250 TLMM pin controller

maintainers:
  - Bjorn Andersson <andersson@kernel.org>

description:
  Top Level Mode Multiplexer pin controller in Qualcomm SM7250 SoC.

allOf:
  - $ref: /schemas/pinctrl/qcom,tlmm-common.yaml#

properties:
  compatible:
    const: qcom,sm7250-tlmm

  reg:
    maxItems: 3

  reg-names:
    items:
      - const: south
      - const: west
      - const: east

  interrupts:
    maxItems: 1

  gpio-reserved-ranges:
    minItems: 1
    maxItems: {(GPIO_LINES + 1) // 2}

  gpio-line-names:
    maxItems: {GPIO_LINES}

patternProperties:
  "-state$":
    oneOf:
      - $ref: "#/$defs/qcom-sm7250-tlmm-state"
      - patternProperties:
          "-pins$":
            $ref: "#/$defs/qcom-sm7250-tlmm-state"
        additionalProperties: false

$defs:
  qcom-sm7250-tlmm-state:
    type: object
    description:
      Pinctrl node's client devices use subnodes for desired pin configuration.
      Client device subnodes use below standard properties.
    $ref: qcom,tlmm-common.yaml#/$defs/qcom-tlmm-state
    unevaluatedProperties: false

    properties:
      pins:
        description:
          List of gpio pins affected by the properties specified in this
          subnode.
        items:
          oneOf:
            - pattern: "{gpio_pat}"
            - enum:
{yaml_list(specials, 16)}
        minItems: 1
        maxItems: 36

      function:
        description:
          Specify the alternative function to be configured for the specified
          pins.

        enum:
{yaml_list(functions, 10)}

    required:
      - pins

required:
  - compatible
  - reg
  - reg-names

unevaluatedProperties: false

examples:
  - |
    #include <dt-bindings/interrupt-controller/arm-gic.h>

    tlmm: pinctrl@f100000 {{
        compatible = "qcom,sm7250-tlmm";
        reg = <0x0f100000 0x300000>,
              <0x0f500000 0x300000>,
              <0x0f900000 0x300000>;
        reg-names = "south", "west", "east";
        interrupts = <GIC_SPI 208 IRQ_TYPE_LEVEL_HIGH>;
        gpio-ranges = <&tlmm 0 0 {GPIO_LINES}>; /* GPIOs + ufs_reset */
        gpio-controller;
        #gpio-cells = <2>;
        interrupt-controller;
        #interrupt-cells = <2>;
        wakeup-parent = <&pdc>;

        gpio-wo-state {{
            pins = "gpio1";
            function = "gpio";
        }};

        uart-w-state {{
            rx-pins {{
                pins = "gpio37";
                function = "qup02";
                bias-pull-up;
            }};

            tx-pins {{
                pins = "gpio36";
                function = "qup02";
                bias-disable;
            }};
        }};
    }};
...
'''
open(OUT_YAML, 'w').write(yaml)
print(f'pins {len(pins)}, gpios {NGPIOS}, functions {len(functions)}, wake entries {len(wake)}, specials {specials}')
