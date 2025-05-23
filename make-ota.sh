#!/usr/bin/env bash
# Parse the command line arguments
source config.sh

set -eo pipefail

variant=""

# Check if $ROOTFS_PATH exists as a file
if [[ ! -f $METIUCULOUS_ROOTFS ]]; then
    echo "Rootfs tarball does not exist: $METIUCULOUS_ROOTFS"
    exit 1
fi

# Parse the command line arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
    --variant)
        shift
        variant="$1"
        ;;
    --cert)
        shift
        cert="$1"
        ;;
    --key)
        shift
        key="$1"
        ;;
    *)
        echo "Invalid argument: $key"
        exit 1
        ;;
    esac
    shift
done

# Check if --cert and --key were passed
if [[ -z $cert || -z $key ]]; then
    echo "Both --cert and --key must be passed"
    exit 1
fi

if [[ -z $variant ]]; then
    echo "Variant must be passed"
    exit 1
fi

# Check if $cert and $key exist as files
if [[ ! -f $cert ]]; then
    echo "Certificate file does not exist: $cert"
    exit 1
fi

if [[ ! -f $key ]]; then
    echo "Key file does not exist: $key"
    exit 1
fi

# Check if --version was passed
if [[ $version ]]; then
    bundle_version=$version
else
    bundle_version=$(date -u +'%Y-%m-%dT%H_%M_%S')
fi

echo -e "\e[1;35m"
echo "Bundle Version:  $bundle_version"
echo "Bundle Variant:  $variant"
echo "Bundle Rootfs:   ${METIUCULOUS_ROOTFS}"
echo "Bundle Key:      ${key}"
echo "Bundle Cert:     ${cert}"
echo -e "\e[0m"

echo -e "\e[1;31mIT IS YOUR RESPONSIBILITY TO ENSURE ${cert} EXISTS IN THE ROOTFS\e[0m\n"

rm -rf rauc_build
mkdir -p rauc_build
cp ${METIUCULOUS_ROOTFS} rauc_build/${METIUCULOUS_ROOTFS}
cp rauc-config/hooks.sh rauc_build/hooks.sh

# Write the modified template to a new file
echo -e "\e[1;34mRAUC config:\e[1;32m\n"

echo "\
[update]
compatible=rauc-meticulous-update
version=${bundle_version}
description=${variant}

[bundle]
format=verity

[hooks]
filename=hooks.sh

[image.rootfs]
filename=${METIUCULOUS_ROOTFS}
hooks=post-install
" | tee rauc_build/manifest.raucm

echo -e "\e[0m"

echo -e "\e[1;34mBuilding EMMC bundle:\e[0m"
rauc --cert $cert --key $key --keyring ${RAUC_CONFIG_DIR}/${RAUC_CERT} bundle rauc_build rauc_meticulous_emmc_${variant}_${bundle_version}.raucb
echo -e "Done"

rm -r rauc_build
