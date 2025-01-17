#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import time
import array
import math
import argparse

import usb.core
import usb.util


# ======= Some C-like static constants =======
DFU_ID_VENDOR = 0x4348
DFU_ID_PRODUCT = 0x55e0

EP_OUT_ADDR = 0x02
EP_IN_ADDR = 0x82

USB_MAX_TIMEOUT = 2000

DETECT_CHIP_CMD_V2 = [
    0xa1,
    0x12,
    0x00,
    0x52,
    0x11,
    0x4d,
    0x43,
    0x55,
    0x20,
    0x49,
    0x53,
    0x50,
    0x20,
    0x26,
    0x20,
    0x57,
    0x43,
    0x48,
    0x2e,
    0x43,
    0x4e]
END_FLASH_CMD_V2 = [0xa2, 0x01, 0x00, 0x00]
RESET_RUN_CMD_V2 = [0xa2, 0x01, 0x00, 0x01]
SEND_KEY_CMD_V20 = [0xa3, 0x30, 0x00]
SEND_KEY_CMD_V23 = [0xa3, 0x38, 0x00] + [0x00] * (0x38)
SEND_KEY_CMD_V26 = [0xa3, 0x1e, 0x00] + [0x00] * 30
ERASE_CHIP_CMD_V2 = [0xa4, 0x01, 0x00, 0x08]
ERASE_CHIP_CMD_V2_32BIT = [0xa4, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00]
WRITE_CMD_V2 = [0xa5, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
VERIFY_CMD_V2 = [0xa6, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
READ_CFG_CMD_V2 = [0xa7, 0x02, 0x00, 0x1f, 0x00]

CH55X_IC_REF = {}
CH55X_IC_REF[0x51] = {
    'device_name': 'CH551',
    'device_flash_size': 10240,
    'device_dataflash_size': 128,
    'chip_id': 0x51}
CH55X_IC_REF[0x52] = {
    'device_name': 'CH552',
    'device_flash_size': 16384,
    'device_dataflash_size': 128,
    'chip_id': 0x52}
CH55X_IC_REF[0x53] = {
    'device_name': 'CH553',
    'device_flash_size': 10240,
    'device_dataflash_size': 128,
    'chip_id': 0x53}
CH55X_IC_REF[0x54] = {
    'device_name': 'CH554',
    'device_flash_size': 14336,
    'device_dataflash_size': 128,
    'chip_id': 0x54}
CH55X_IC_REF[0x59] = {
    'device_name': 'CH559',
    'device_flash_size': 61440,
    'device_dataflash_size': 128,
    'chip_id': 0x59}
CH55X_IC_REF[0x3f] = {
    'device_name': 'CH32V103',
    'device_flash_size': 64*1024,
    'chip_id': 0x3f,
    'erase_required_pages': True}
CH55X_IC_REF[0x71] = {
    'device_name': 'CH571',
    'device_flash_size': 192*1024,
    'chip_id': 0x71,
    'erase_required_pages': True}
CH55X_IC_REF[0x73] = {
    'device_name': 'CH573',
    'device_flash_size': 448*1024,
    'chip_id': 0x73,
    'erase_required_pages': True}
CH55X_IC_REF[0x79] = {
    'device_name': 'CH579',
    'device_flash_size': 250*1024,
    'chip_id': 0x79,
    'erase_required_pages': True}
CH55X_IC_REF[0x82] = {
    'device_name': 'CH582',
    'device_flash_size': 448*1024,
    'chip_id': 0x82,
    'erase_required_pages': True}
    
# =============================================
def __get_dfu_device(idVendor=DFU_ID_VENDOR, idProduct=DFU_ID_PRODUCT):
    dev = usb.core.find(idVendor=idVendor, idProduct=idProduct)
    if dev is None:
        return (None, 'NO_DEV_FOUND')
    try:
        if dev.is_kernel_driver_active(0):
            try:
                dev.detach_kernel_driver(0)
            except usb.core.USBError:
                return (None, 'USB_ERROR_CANNOT_DETACH_KERNEL_DRIVER')
    except BaseException:
        pass  # Windows dont need detach

    try:
        dev.set_configuration()
    except usb.core.USBError:
        return (None, 'USB_ERROR_CANNOT_SET_CONFIG')

    try:
        usb.util.claim_interface(dev, 0)
    except usb.core.USBError:
        return (None, 'USB_ERROR_CANNOT_CLAIM_INTERFACE')

    return (dev, '')


def __detect_ch55x_v2(dev):
    dev.write(EP_OUT_ADDR, DETECT_CHIP_CMD_V2)
    ret = dev.read(EP_IN_ADDR, 6, USB_MAX_TIMEOUT)
    try:
        return CH55X_IC_REF[ret[4]]
    except KeyError:
        return None


def __read_cfg_ch55x_v2(dev):
    dev.write(EP_OUT_ADDR, READ_CFG_CMD_V2)
    ret = dev.read(EP_IN_ADDR, 30, USB_MAX_TIMEOUT)

    ver_str = 'V%d.%d%d' % (ret[19], ret[20], ret[21])
    if ret[19] == 2 and ret[20] >= 6:
        chk_sum = (ret[22] + ret[23] + ret[24] + ret[25] + ret[26] + ret[27] + ret[28] + ret[29]) % 256
    else:
        chk_sum = (ret[22] + ret[23] + ret[24] + ret[25]) % 256
    return (ver_str, chk_sum)


def __write_key_ch55x_v20(dev, chk_sum):
    SEND_KEY_CMD_V20 = SEND_KEY_CMD_V20 + [chk_sum] * 0x30

    dev.write(EP_OUT_ADDR, SEND_KEY_CMD_V20)
    ret = dev.read(EP_IN_ADDR, 6, USB_MAX_TIMEOUT)
    if ret[3] == 0:
        return True
    else:
        return None


def __write_key_ch55x_v23(dev, key_cmd):
    dev.write(EP_OUT_ADDR, key_cmd)
    ret = dev.read(EP_IN_ADDR, 6, USB_MAX_TIMEOUT)
    if ret[3] == 0:
        return True
    else:
        return None


def __erase_chip_ch55x_v2(dev, page_count=None, timeout=None):
    command = None
    if page_count == None:
        command = ERASE_CHIP_CMD_V2
    else:
        if page_count < 256:
            command = ERASE_CHIP_CMD_V2
            command[3] = page_count
        else:
            command = ERASE_CHIP_CMD_V2_32BIT
            command[3] = page_count % 256
            command[4] = (page_count >> 8) % 256
            command[5] = (page_count >> 16) % 256
            command[6] = (page_count >> 24) % 256
    
    if timeout == None:
        timeout = USB_MAX_TIMEOUT
    
    dev.write(EP_OUT_ADDR, command)
    ret = dev.read(EP_IN_ADDR, 6, timeout)
    if ret[3] == 0:
        return True
    else:
        return None


def __write_flash_ch55x_v20(dev, chk_sum, chip_id, payload):
    # Payload needs to be padded, 56 is a good number
    payload = payload + [0] * \
        ((math.ceil(len(payload) / 56) * 56) - len(payload))
    file_length = len(payload)

    for index in range(file_length):
        if index % 8 == 7:
            payload[index] = (
                payload[index] ^ (
                    (chk_sum + chip_id) % 256)) % 256

    left_len = file_length
    curr_addr = 0

    while curr_addr < file_length:

        if left_len >= 56:
            pkt_length = 56
        else:
            pkt_length = left_len

        __WRITE_CMD_V2 = WRITE_CMD_V2
        __WRITE_CMD_V2[1] = pkt_length + 5
        __WRITE_CMD_V2[3] = curr_addr % 256
        __WRITE_CMD_V2[4] = (curr_addr >> 8) % 256
        __WRITE_CMD_V2[7] = left_len % 256
        __WRITE_CMD_V2 = __WRITE_CMD_V2 + \
            payload[curr_addr:curr_addr + pkt_length]

        dev.write(EP_OUT_ADDR, __WRITE_CMD_V2)
        ret = dev.read(EP_IN_ADDR, 6, USB_MAX_TIMEOUT)

        curr_addr = curr_addr + pkt_length
        left_len = left_len - pkt_length

        if ret[4] != 0x00:
            return None

    return file_length


def __write_flash_ch55x_v23(dev, chk_sum, chip_id, payload):
    # Payload needs to be padded, 56 is a good number
    payload = payload + [0] * \
        ((math.ceil(len(payload) / 56) * 56) - len(payload))
    file_length = len(payload)

    for index in range(file_length):
        if index % 8 == 7:
            payload[index] = (
                payload[index] ^ (
                    (chk_sum + chip_id) % 256)) % 256
        else:
            payload[index] = (payload[index] ^ chk_sum) % 256

    left_len = file_length
    curr_addr = 0

    while curr_addr < file_length:

        if left_len >= 56:
            pkt_length = 56
        else:
            pkt_length = left_len

        __WRITE_CMD_V2 = WRITE_CMD_V2
        __WRITE_CMD_V2[1] = pkt_length + 5
        __WRITE_CMD_V2[3] = curr_addr % 256
        __WRITE_CMD_V2[4] = (curr_addr >> 8) % 256
        __WRITE_CMD_V2[5] = (curr_addr >> 16) % 256
        __WRITE_CMD_V2[7] = left_len % 256
        __WRITE_CMD_V2 = __WRITE_CMD_V2 + \
            payload[curr_addr:curr_addr + pkt_length]

        dev.write(EP_OUT_ADDR, __WRITE_CMD_V2)
        ret = dev.read(EP_IN_ADDR, 6, USB_MAX_TIMEOUT)
        
        curr_addr = curr_addr + pkt_length
        left_len = left_len - pkt_length

        if ret[4] != 0x00:
            return None

    if chip_id == 0x3f:
        # My CH32V103 with BT V2.60 will fail to verify without this empty write
        # My CH579 with BT V2.61 will fail to verify *with* this empty write
        # I'm not sure if this is required due to MCU or bootloader version
        # So for now am guarding it with the MCU chip id
        __WRITE_CMD_V2 = WRITE_CMD_V2
        __WRITE_CMD_V2[1] = 5
        __WRITE_CMD_V2[3] = file_length % 256
        __WRITE_CMD_V2[4] = (file_length >> 8) % 256
        __WRITE_CMD_V2[5] = (file_length >> 16) % 256
        __WRITE_CMD_V2[7] = 0
        dev.write(EP_OUT_ADDR, __WRITE_CMD_V2)
        ret = dev.read(EP_IN_ADDR, 6, USB_MAX_TIMEOUT)
        if ret[4] != 0x00:
            return None
    
    return file_length


def __verify_flash_ch55x_v20(dev, chk_sum, chip_id, payload):
    # Payload needs to be padded, 56 is a good number
    payload = payload + [0] * \
        ((math.ceil(len(payload) / 56) * 56) - len(payload))
    file_length = len(payload)

    for index in range(file_length):
        if index % 8 == 7:
            payload[index] = (
                payload[index] ^ (
                    (chk_sum + chip_id) % 256)) % 256

    left_len = file_length
    curr_addr = 0

    while curr_addr < file_length:

        if left_len >= 56:
            pkt_length = 56
        else:
            pkt_length = left_len

        __VERIFY_CMD_V2 = VERIFY_CMD_V2
        __VERIFY_CMD_V2[1] = pkt_length + 5
        __VERIFY_CMD_V2[3] = curr_addr % 256
        __VERIFY_CMD_V2[4] = (curr_addr >> 8) % 256
        __VERIFY_CMD_V2[7] = left_len % 256
        __VERIFY_CMD_V2 = __VERIFY_CMD_V2 + \
            payload[curr_addr:curr_addr + pkt_length]

        dev.write(EP_OUT_ADDR, __VERIFY_CMD_V2)
        ret = dev.read(EP_IN_ADDR, 6, USB_MAX_TIMEOUT)

        curr_addr = curr_addr + pkt_length
        left_len = left_len - pkt_length

        if ret[4] != 0x00:
            return None

    return file_length


def __verify_flash_ch55x_v23(dev, chk_sum, chip_id, payload):
    # Payload needs to be padded, 56 is a good number
    payload = payload + [0] * \
        ((math.ceil(len(payload) / 56) * 56) - len(payload))
    file_length = len(payload)

    for index in range(file_length):
        if index % 8 == 7:
            payload[index] = (
                payload[index] ^ (
                    (chk_sum + chip_id) % 256)) % 256
        else:
            payload[index] = (payload[index] ^ chk_sum) % 256

    left_len = file_length
    curr_addr = 0

    while curr_addr < file_length:

        if left_len >= 56:
            pkt_length = 56
        else:
            pkt_length = left_len

        __VERIFY_CMD_V2 = VERIFY_CMD_V2
        __VERIFY_CMD_V2[1] = pkt_length + 5
        __VERIFY_CMD_V2[3] = curr_addr % 256
        __VERIFY_CMD_V2[4] = (curr_addr >> 8) % 256
        __VERIFY_CMD_V2[5] = (curr_addr >> 16) % 256
        __VERIFY_CMD_V2[7] = left_len % 256
        __VERIFY_CMD_V2 = __VERIFY_CMD_V2 + \
            payload[curr_addr:curr_addr + pkt_length]

        dev.write(EP_OUT_ADDR, __VERIFY_CMD_V2)
        ret = dev.read(EP_IN_ADDR, 6, USB_MAX_TIMEOUT)
        
        curr_addr = curr_addr + pkt_length
        left_len = left_len - pkt_length

        if ret[4] != 0x00:
            return None

    return file_length


def __end_flash_ch55x_v2(dev):
    dev.write(EP_OUT_ADDR, END_FLASH_CMD_V2)
    ret = dev.read(EP_IN_ADDR, 6, USB_MAX_TIMEOUT)
    if ret[4] != 0x00:
        return None
    else:
        return True


def __restart_run_ch55x_v2(dev):
    dev.write(EP_OUT_ADDR, RESET_RUN_CMD_V2)


def main():
    parser = argparse.ArgumentParser(
        description="USBISP Tool For WinChipHead CH55x.")
    parser.add_argument(
        '-f',
        '--file',
        type=str,
        default='',
        help="The target file to be flashed. This must be a binary file (hex files are not supported).")
    parser.add_argument(
        '-r',
        '--reset_after_flash',
        action='store_true',
        default=False,
        help="Reset after finsh flash.")
    args = parser.parse_args()

    ret = __get_dfu_device()
    if ret[0] is None:
        print('Failed to get device, please check your libusb installation.')
        sys.exit(-1)
        
    dev = ret[0]

    wch_dev = __detect_ch55x_v2(dev)
    if wch_dev is None:
        print('Unable to detect CH55x.')
        print('Welcome to report this issue with a screen shot from the official CH55x tool.')
        sys.exit(-1)

    print('Found %s.' % wch_dev['device_name'])
    chip_id = wch_dev['chip_id']

    ret = __read_cfg_ch55x_v2(dev)
    chk_sum = ret[1]
    print('BTVER: %s.' % ret[0])

    try:
        btver = float(ret[0][1:])
    except:
        btver = 0

    if args.file != '':
        payload = list(open(args.file, 'rb').read())
        if args.file.endswith('.hex') or args.file.endswith('.ihx') or payload[0]==58:
            print("WARNING: This looks like a hex file. This tool only supports binary files.")
        if len(payload) > wch_dev['device_flash_size']: 
            print("WARNING: The file size %i exceeds the device's device_flash_size %i" % (len(payload), wch_dev['device_flash_size']))
        if ret[0] in ['V2.30']:
            ret = __write_key_ch55x_v20(dev, chk_sum)
            if ret is None:
                sys.exit('Failed to write key to CH55x.')

            ret = __erase_chip_ch55x_v2(dev)
            if ret is None:
                sys.exit('Failed to erase CH55x.')

            ret = __write_flash_ch55x_v20(dev, chk_sum, chip_id, payload)
            if ret is None:
                sys.exit('Failed to flash firmware of CH55x.')

            ret = __verify_flash_ch55x_v20(dev, chk_sum, chip_id, payload)
            if ret is None:
                sys.exit('Failed to verify firmware of CH55x.')
        else:
            if ret[0] in ['V2.31', 'V2.40', 'V2.60', 'V2.61', 'V2.70', 'V2.80']:
                if btver >= 2.6:
                    ret = __write_key_ch55x_v23(dev, SEND_KEY_CMD_V26)
                else:
                    ret = __write_key_ch55x_v23(dev, SEND_KEY_CMD_V23)
                
                if ret is None:
                    sys.exit('Failed to write key to CH55x.')

                page_count = None
                if wch_dev.get('erase_required_pages', None):
                    page_count = math.ceil(len(payload) / 1024)

                ret = __erase_chip_ch55x_v2(dev, page_count, wch_dev.get('erase_timeout', None))
                if ret is None:
                    sys.exit('Failed to erase CH55x.')

                ret = __write_flash_ch55x_v23(dev, chk_sum, chip_id, payload)
                if ret is None:
                    sys.exit('Failed to flash firmware of CH55x.')

                ret = __verify_flash_ch55x_v23(dev, chk_sum, chip_id, payload)
                if ret is None:
                    sys.exit('Failed to verify firmware of CH55x.')
            else:
                sys.exit('Bootloader version not supported.')

        ret = __end_flash_ch55x_v2(dev)
        if ret is None:
            sys.exit('Failed to end flash process.')

        print('Flash done.')

        if args.reset_after_flash:
            __restart_run_ch55x_v2(dev)
            print('Restart and run.')
