	.global _zephry_bin_start_
	.global _entry_point_rtk_
	.global _signature_rtk_

	.section .zephyr.bin, "ax"
_zephry_bin_start_:
	.incbin "zephyr.bin"
	
	.section .rtk.entry, "ax"
_entry_table_rtk_:
	.long _signature_rtk_
	.long _entry_point_rtk_

	.section .rtk.signature, "a"
_signature_rtk_:
	.ascii "AmebaPro2"
	.byte 0xFF 

	.text
	.thumb
	.thumb_func
	.section .rtk.entry.text , "ax"
	.align 8 
	.globl    _entry_point_rtk_
	.type    _entry_point_rtk_, %function
_entry_point_rtk_:
	ldr r2, =_zephry_bin_start_
	ldr r1, [r2]         
	ldr r3, [r2, #4]     
	cmp r3, #0            
	beq error_handler      
	mov sp, r1
	bx	r3

error_handler:
	b error_handler
