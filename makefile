FILE=a

CMD='podman --volume "$(pwd)/src:/home/wineuser/app/src" --volume "$(pwd)/bin:/home/wineuser/app/bin" run -t --rm asm68k /p /i /w /ov+ /oos+ /oop+ /oow+ /ooz+ /ooaq+ /oosq+ /oomq+ /ow+ ${FILE}.s,../bin/${FILE}.bin,../bin/${FILE}'

emu: ${FILE}.bin
	mame genesis -cart ./bin/${FILE}.bin
	#wine ./Emulator/gens_kmod/gens.exe "$$(pwd)/bin/${FILE}.bin"

#p    Produce pure binary output file
#i    Show an information window while assembling. Only compatible with pure 16-bit MSDOS.
#w    Write all equates to the listing file.
#v+   Write local labels to symbol file
#os+  Short branch optimisation
#op+  PC relative optimisation
#ow+  Print warnings
#oz+  Zero offset optimisation
#oaq+ Addq optimisation
#osq+ Subq optimisation
#omq+ Moveq optimisation
#ow+  Absolute word addressing optimisation
#asm68k.exe
${FILE}.bin: ./src/${FILE}.s
	$(CMD) /p /i /w /ov+ /oos+ /oop+ /oow+ /ooz+ /ooaq+ /oosq+ /oomq+ /ow+ ,./src/${FILE}.s,./bin/${FILE}.bin,./bin/${FILE}

debug: ./src/${FILE}.s
	$(CMD) /i /w /ov+ /oos+ /oop+ /oow+ /ooz+ /ooaq+ /oosq+ /oomq+ /ow+ ./src/${FILE}.s,./bin/${FILE}.db.bin,./bin/${FILE}.db

debugMame: debug
	mame genesis -debug -cart ./bin/${FILE}.db.bin

all: ${FILE}.bin

clean:
	rm ./bin/*
