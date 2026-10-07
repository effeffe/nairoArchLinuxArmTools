#!/usr/bin/env python3
"""Rebuild the nairo work as a commit series (one-off helper)."""
import os, re, subprocess, sys, tarfile, io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
K = os.path.join(ROOT, 'linux')
MSG = os.path.join(ROOT, 'commit-msgs')
BACKUP = sys.argv[1]
SMB5 = sys.argv[2]
ORIG_NVT = os.path.join(ROOT, 'tools/src/sm8150-mainline/drivers/input/touchscreen/nt36523')

final = {}
with tarfile.open(os.path.join(BACKUP, 'tree.tar')) as t:
    for m in t.getmembers():
        if m.isfile():
            final[m.name] = t.extractfile(m).read()

def git(*a, **kw):
    r = subprocess.run(['git', '-C', K] + list(a), capture_output=True, text=True, **kw)
    if r.returncode:
        sys.exit(f"git {' '.join(a)} failed:\n{r.stdout}{r.stderr}")
    return r.stdout

def put(path, data):
    p = os.path.join(K, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'wb').write(data if isinstance(data, bytes) else data.encode())
    git('add', path)

def take(*paths):
    for p in paths:
        put(p, final[p])

def commit(n):
    git('commit', '-q', '-F', os.path.join(MSG, n))
    print(n, git('log', '-1', '--format=%h %s').strip())

# --- dtsi intermediate versions ---------------------------------------
DTSI = 'arch/arm64/boot/dts/qcom/sm7250.dtsi'
F = final[DTSI].decode()

def block(text, start_pat):
    m = re.search(r'^(\t+)' + re.escape(start_pat) + r'.*\{\n', text, re.M)
    assert m, start_pat
    ind = m.group(1)
    end = text.index('\n' + ind + '};\n', m.end()) + len('\n' + ind + '};\n')
    if text[end:end + 1] == '\n':
        end += 1
    return text[m.start():end]

# node label patterns (located in the current text at removal time) or literal lines
BLOCKS = {
    'idle': [],
    'tlmm': ['tlmm: pinctrl@f100000'],
    'smmu': ['apps_smmu: iommu@15000000'],
    'usb':  ['usb_1_hsphy: phy@88e3000', 'usb_1: usb@a600000'],
    'ufs':  ['ufs_mem_hc: ufshc@1d84000', 'ufs_mem_phy: phy@1d87000'],
    'sdhc': ['sdhc_2: mmc@8804000', 'sdc2_default_state: sdc2-default-state',
             'sdc2_sleep_state: sdc2-sleep-state'],
    'spi':  ['spi7: spi@984000', 'qup_spi7_default: qup-spi7-default-state',
             'LINE:\t\t\tiommus = <&apps_smmu 0x23 0x0>;\n'],
}
ORDER = ['idle', 'tlmm', 'smmu', 'usb', 'ufs', 'sdhc', 'spi']

def dtsi_upto(stage):
    t = F
    for later in reversed(ORDER[ORDER.index(stage) + 1:]):	# nested blocks first
        for pat in BLOCKS[later]:
            b = pat[5:].encode().decode('unicode_escape') if pat.startswith('LINE:') else block(t, pat)
            assert b in t, (later, pat)
            t = t.replace(b, '', 1)
    if ORDER.index(stage) < ORDER.index('idle') + 0:
        pass
    return t

def dtsi_before_idle():
    t = dtsi_upto('idle')
    return t.replace('<0x41002244>', '<0x41001244>').replace('<0x4100c244>', '<0x4100b244>')

head_dtsi = git('show', 'HEAD:' + DTSI)
assert dtsi_before_idle() == head_dtsi, 'dtsi reconstruction does not match HEAD'

# --- series -----------------------------------------------------------
take('Documentation/devicetree/bindings/pinctrl/qcom,sm7250-tlmm.yaml'); commit('01')
take('drivers/pinctrl/qcom/pinctrl-sm7250.c', 'drivers/pinctrl/qcom/Kconfig.msm',
     'drivers/pinctrl/qcom/Makefile'); commit('02')
take('Documentation/devicetree/bindings/iommu/arm,smmu.yaml'); commit('03')
take('Documentation/devicetree/bindings/phy/qcom,usb-snps-femto-v2.yaml'); commit('04')
take('Documentation/devicetree/bindings/usb/qcom,snps-dwc3.yaml'); commit('05')
take('Documentation/devicetree/bindings/phy/qcom,sc8280xp-qmp-ufs-phy.yaml'); commit('06')
take('Documentation/devicetree/bindings/ufs/qcom,sc7180-ufshc.yaml'); commit('07')
take('Documentation/devicetree/bindings/mmc/qcom,sdhci-msm.yaml'); commit('08')
take('drivers/phy/qualcomm/phy-qcom-qmp-ufs.c'); commit('09')
take('drivers/ufs/host/ufs-qcom.c'); commit('10')

# SMB5 series from the list, keeping its authors and their sign-offs
for p in ('Documentation/devicetree/bindings/power/supply/qcom,pmi8998-charger.yaml',
          'drivers/power/supply/Kconfig', 'drivers/power/supply/qcom_smbx.c'):
    git('checkout', 'HEAD', '--', p)
git('am', '-q', SMB5)
print('am', git('log', '-2', '--format=%h %an: %s').strip().replace('\n', ' | '))
for p in ('Documentation/devicetree/bindings/power/supply/qcom,pmi8998-charger.yaml',
          'drivers/power/supply/Kconfig', 'drivers/power/supply/qcom_smbx.c'):
    assert open(os.path.join(K, p), 'rb').read() == final[p], p

# touch driver: verbatim import, then our changes
D = 'drivers/input/touchscreen/nt36xxx-spi/'
for f in sorted(os.listdir(ORIG_NVT)):
    put(D + f, open(os.path.join(ORIG_NVT, f), 'rb').read())
take('drivers/input/touchscreen/Kconfig', 'drivers/input/touchscreen/Makefile'); commit('13')
for f in ('Kconfig', 'Makefile', 'nt36xxx.c', 'nt36xxx.h', 'nt36xxx_fw_update.c', 'nt36xxx_mem_map.h'):
    take(D + f)
commit('14')

for stage, n in zip(ORDER, ['15', '16', '17', '18', '19', '20', '21']):
    put(DTSI, dtsi_upto(stage)); commit(n)
assert open(os.path.join(K, DTSI), 'rb').read() == final[DTSI]

take('arch/arm64/boot/dts/qcom/pm7250b.dtsi'); commit('22')
take('Documentation/devicetree/bindings/arm/qcom.yaml'); commit('23')
take('arch/arm64/boot/dts/qcom/sm7250-motorola-nairo.dts',
     'arch/arm64/boot/dts/qcom/sm7250-motorola-nairo-dtbo-sink.dtsi',
     'arch/arm64/boot/dts/qcom/Makefile'); commit('24')
take('arch/arm64/configs/nairo.config'); commit('25')

left = git('status', '--short')
print('remaining changes:\n' + (left or '(none)'))
