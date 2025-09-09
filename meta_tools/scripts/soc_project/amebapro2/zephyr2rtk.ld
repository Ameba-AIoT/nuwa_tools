
DDR_SIZE = 128;

DDR_END = 0x70000000 + (DDR_SIZE)*1024*1024;

/* FPGA Linker script to configure memory regions.  */
MEMORY
{					  
  VOE    (rwx)          : ORIGIN = 0x70000000, LENGTH = 0x70100000 - 0x70000000		/*  reserved for VOE */

  DDR    (rwx) 			: ORIGIN = 0x70100000, LENGTH = DDR_END - 0x70100000 
}

SECTIONS
{
	.zephyr :
	{
		KEEP(*(.zephyr.bin))
	} > DDR
	
	.rtk :
	{
		KEEP(*(.rtk.*))
	} > DDR
}
