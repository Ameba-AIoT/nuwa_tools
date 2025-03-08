#!/bin/bash 

################
# Library
################
Usage() {
    echo "Usage: $0 [Image Name]"
}

################
# Main
################
if [ "$#" -lt 1 ]; then
   Usage
   exit 1
fi

cd $(dirname "$(realpath $0)")

# Get Parameters
COMPILEOS=$(uname -o)
if [ "$COMPILEOS" == "GNU/Linux" ]; then
	ELF2BIN=./elf2bin
else
	ELF2BIN=./elf2bin.exe
fi

if [ ! -f $ELF2BIN ]; then
	echo Error elf2bin path
	exit
fi

IMAGE_FILENAME=$(basename $1)
KM4_IMG_DIR=$(dirname $1)
MANIFEST_JSON=./manifest.json
chmod +x $ELF2BIN

if [ "$IMAGE_FILENAME" == "km0_image2_all.bin" ] || [ "$IMAGE_FILENAME" == "km4_image2_all.bin" ]; then
	if [ ! -f $KM4_IMG_DIR/km4_image2_all.bin ]; then
		exit
	fi
	
	if [ ! -f $KM4_IMG_DIR/km0_image2_all.bin ]; then
		exit
	fi

	if [ -f $KM4_IMG_DIR/km0_km4_app.bin ]; then
		rm -rf $KM4_IMG_DIR/km0_km4_app.bin
	fi

	if [ -f $KM4_IMG_DIR/km4_image3_all.bin ]; then
		cat $KM4_IMG_DIR/km0_image2_all.bin $KM4_IMG_DIR/km4_image2_all.bin $KM4_IMG_DIR/km4_image3_all.bin > $KM4_IMG_DIR/km0_km4_app_tmp.bin
	else
		cat $KM4_IMG_DIR/km0_image2_all.bin $KM4_IMG_DIR/km4_image2_all.bin > $KM4_IMG_DIR/km0_km4_app_tmp.bin
	fi

	$ELF2BIN cert $MANIFEST_JSON $MANIFEST_JSON $KM4_IMG_DIR/cert.bin 0 app
	$ELF2BIN manifest $MANIFEST_JSON $MANIFEST_JSON $KM4_IMG_DIR/km0_km4_app_tmp.bin $KM4_IMG_DIR/manifest.bin app
	if [ ! -f $KM4_IMG_DIR/manifest.bin ]; then
		exit
	fi
	$ELF2BIN rsip $KM4_IMG_DIR/km0_image2_all.bin $KM4_IMG_DIR/km0_image2_all_en.bin 0x0c000000 $MANIFEST_JSON app
	$ELF2BIN rsip $KM4_IMG_DIR/km4_image2_all.bin $KM4_IMG_DIR/km4_image2_all_en.bin 0x0e000000 $MANIFEST_JSON app

	if [ -f $KM4_IMG_DIR/km4_image3_all_en.bin ]; then
		cat $KM4_IMG_DIR/cert.bin $KM4_IMG_DIR/manifest.bin $KM4_IMG_DIR/km0_image2_all.bin $KM4_IMG_DIR/km4_image2_all.bin $KM4_IMG_DIR/km4_image3_all.bin > $KM4_IMG_DIR/km0_km4_app_ns.bin
		cat $KM4_IMG_DIR/cert.bin $KM4_IMG_DIR/manifest.bin $KM4_IMG_DIR/km0_image2_all_en.bin $KM4_IMG_DIR/km4_image2_all_en.bin $KM4_IMG_DIR/km4_image3_all_en.bin > $KM4_IMG_DIR/km0_km4_app.bin
	else
		cat $KM4_IMG_DIR/cert.bin $KM4_IMG_DIR/manifest.bin $KM4_IMG_DIR/km0_image2_all.bin $KM4_IMG_DIR/km4_image2_all.bin > $KM4_IMG_DIR/km0_km4_app_ns.bin
		cat $KM4_IMG_DIR/cert.bin $KM4_IMG_DIR/manifest.bin $KM4_IMG_DIR/km0_image2_all_en.bin $KM4_IMG_DIR/km4_image2_all_en.bin > $KM4_IMG_DIR/km0_km4_app.bin
	fi

	rm -rf $KM4_IMG_DIR/cert.bin $KM4_IMG_DIR/manifest.bin $KM4_IMG_DIR/km0_km4_app_tmp.bin $KM4_IMG_DIR/km0_image2_all_en.bin $KM4_IMG_DIR/km4_image2_all_en.bin
fi
