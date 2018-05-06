from infi.instruct.struct import Struct, FieldListContainer, AnonymousField
from infi.instruct.buffer import Buffer
import binascii


class OutputFormatter(object):

    def format(self, item):
        """ Renders the output as string """
        raise NotImplementedError()

    def _to_bytes(self, item):
        """ Utility method that converts the output to a byte sequence """
        data = str(type(item).write_to_string(item)) if isinstance(item, Struct) else \
               str(item.pack()) if isinstance(item, Buffer) else \
               '' if item is None else str(item)
        return data

    def _to_dict(self, item):
        """ Utility method that converts the output to a dict """
        if isinstance(item, Buffer):
            ret = {}
            fields = item._all_fields()
            for field in fields:
                ret[field.attr_name()] = self._to_dict(getattr(item, field.attr_name()))
            return ret

        if isinstance(item, Struct):
            ret = {}
            for field in item._container_.fields:
                if hasattr(field, 'name'):
                    ret[field.name] = self._to_dict(field.get_value(item))
                elif isinstance(field, FieldListContainer):
                    for inner_field in field.fields:
                        if not isinstance(inner_field, AnonymousField):
                            ret[inner_field.name] = self._to_dict(inner_field.get_value(item))
            return ret

        if isinstance(item, bytearray):
            return '0x' + binascii.hexlify(item) if item else ''

        if isinstance(item, list):
            return [self._to_dict(x) for x in item]

        return item


class RawOutputFormatter(OutputFormatter):

    def format(self, item):
        return self._to_bytes(item)


class HexOutputFormatter(OutputFormatter):

    def format(self, item):
        from hexdump import hexdump
        return hexdump(self._to_bytes(item), result='return')


class JsonOutputFormatter(OutputFormatter):

    def format(self, item):
        from json import dumps
        return dumps(self._to_dict(item), indent=4, sort_keys=True)


class DefaultOutputFormatter(JsonOutputFormatter):

    def format(self, item):
        return super(DefaultOutputFormatter, self).format(item).replace('"', '').replace(',', '')


class ErrorOutputFormatter(OutputFormatter):

    def format(self, item):
        return 'ERROR: %s (%s)' % (item.sense_key, item.additional_sense_code.code_name)


class ReadcapOutputFormatter(OutputFormatter):

    def format(self, item):
        data = self._to_dict(item)
        lines = [
            'Read Capacity results:',
            '   Last logical block address={lastblock} ({lastblock:#x}), Number of blocks={numblocks}',
            '   Logical block length={length} bytes',
            'Hence:',
            '   Device size: {size} bytes, {size_mb:.1f} MiB, {size_gb:.2f} GB'
        ]
        if 'prot_en' in data:
            lines.insert(1, '   Protection: prot_en={prot_en}, p_type={p_type}, p_i_exponent={p_i_exponent}')
            if data['prot_en']:
                lines[1] += (' [type {protection} protection]')
            lines.insert(2, '   Logical block provisioning: lbpme={tpe}, lbprz={troz}')
            lines.insert(5, '   Logical blocks per physical block exponent={logical_blocks_per_physical_block}')
            lines.insert(6, '   Lowest aligned logical block address={lowest_address}')
        params = dict(
            data,
            lastblock=data['last_logical_block_address'],
            numblocks=data['last_logical_block_address'] + 1,
            length=data['block_length_in_bytes'],
            protection=data.get('p_type', 0) + 1,
            lowest_address=256 * data.get('lowest_aligned_lba_msb', 0) + data.get('lowest_aligned_lba_lsb', 0)
        )
        params['size'] = params['numblocks'] * params['length']
        params['size_mb'] = params['size'] / 1024.0 / 1024.0
        params['size_gb'] = params['size'] / 1000.0 / 1000.0 / 1000.0
        return '\n'.join(lines).format(**params)


class InqOutputFormatter(DefaultOutputFormatter):

    def __init__(self):
        self.SUPPORTED_PAGES = {0x00: self._format_0x00_page,
                                0x80: self._format_0x80_page,
                                0x83: self._format_0x83_page,
                                None: self._format_none_page}

    def _fill_missing_values(self, item):
        # Filling missing obsolete values by reading and parsing the bytes - see spc4r30.pdf Table 139, page 261
        # also see:
        # https://www.ibm.com/support/knowledgecenter/en/STQRQ9/com.ibm.storage.ts4500.doc/ts4500_sref_3584_minqv.html
        # http://www.tldp.org/HOWTO/archived/SCSI-Programming-HOWTO/SCSI-Programming-HOWTO-9.html
        missing_data = {}
        bytes_as_bits = [''.join(reversed(bin(byte)[2:].zfill(8))) for byte in item.pack()]
        missing_data['aerc'] = bytes_as_bits[3][7]
        missing_data['trmtsk'] = bytes_as_bits[3][6]
        missing_data['bque'] = bytes_as_bits[6][7]
        missing_data['vs'] = bytes_as_bits[6][5]
        missing_data['mchngr'] = bytes_as_bits[6][3]
        missing_data['ackreqq'] = bytes_as_bits[6][2]
        missing_data['reladr'] = bytes_as_bits[7][7]
        missing_data['linked'] = bytes_as_bits[7][3]
        missing_data['trandis'] = bytes_as_bits[7][2]
        return missing_data

    def _get_vpd_page_name(self, vpd_page, data):
        from infi.asi.cdb.inquiry.vpd_pages import SCSI_VPD_NAME
        if vpd_page in range(0xb0, 0xc0):  # 0xb0 to 0xbf are per peripheral device type
            page_name = SCSI_VPD_NAME.get(vpd_page, {}).get(data['peripheral_device']['type'], '')
        else:
            page_name = SCSI_VPD_NAME.get(vpd_page, '')
        return page_name

    def _get_designator_output_string(self, designator):
        # Working Draft SCSI Primary Commands - 4 (SPC-4) - Tables 532- 551 (page 615- 624)
        DESIGNATORS_OUTPUT = {
            0x03: {
                0x02: (
                    '      NAA 2, vendor specific identifier A: 0x{vendor_specific_identifier_a:02x}\n'
                    '      IEEE Company_id: 0x{ieee_company_id:02x}\n'
                    '      vendor specific identifier B: 0x{vendor_specific_identifier_b:02x}'
                ),
                0x03:
                    '      NAA 3, Locally assigned:',
                0x05: (
                    '      NAA 5, IEEE Company_id: 0x{ieee_company_id:02x}\n'
                    '      Vendor Specific Identifier: 0x{vendor_specific_identifier:02x}'
                ),
                0x06: (
                    '      NAA 6, IEEE Company_id: 0x{ieee_company_id:02x}\n'
                    '      Vendor Specific Identifier: 0x{vendor_specific_identifier:02x}\n'
                    '      Vendor Specific Identifier Extension: 0x{vendor_specific_identifier_extension:01x}\n'
                    '      [{packed_string}]'
                )
            },
            0x04: '      Relative target port: 0x{relative_target_port_identifier:02x}',
            0x05: '      Target port group: 0x{target_port_group:02x}',
            0x06: '      Logical unit group: {logical_group}',
            0x07: '      MD5 logical unit identifier:\n{md5_logical_identifier}',
            0x08: '      SCSI name string:\n{scsi_name_string}',
            0x0a: '      Locally assigned UUID: {assigned_uuid}',
        }
        if isinstance(DESIGNATORS_OUTPUT[designator['designator_type']], dict):  # NAA has more then 1 possible output
            designator_string = DESIGNATORS_OUTPUT[designator['designator_type']][designator['naa']]
        else:
            designator_string = DESIGNATORS_OUTPUT[designator['designator_type']]
        return designator_string

    def _format_none_page(self, data, item):
        from infi.asi.cdb.inquiry.vpd_pages import SCSI_PERIPHERAL_DEVICE_TYPE, SCSI_VERSION_NAME
        device = data['peripheral_device']
        lines = [
            'standard INQUIRY:',
            '  PQual={pqual}  Device_type={device_type}  RMB={rmb}  version=0x{version:02x}  [{version_name}]',
            '  [AERC={aerc}]  [TrmTsk={trmtsk}]  NormACA={normaca}  HiSUP={hisup}  Resp_data_format={resp_data_format}',
            '  SCCS={sccs}  ACC={acc}  TPGS={tpgs}  3PC={threepc}  Protect={protect}  [BQue={bque}]',
            '  EncServ={enc_serv}  MultiP={multi_p} (VS={vs})  [MChngr={mchngr}]  [ACKREQQ={ackreqq}]  Addr16={addr16}',
            '  [RelAdr={reladr}]  WBus16={wbus16}  Sync={sync}  Linked={linked}  [TranDis={trandis}]  CmdQue={cmd_que}',
            '  [SPI: Clocking=0x{extended[clocking]:01x}  QAS={extended[qas]}  IUS={extended[ius]}]'
            if data['extended'] is not None else '',
            '    length={size} (0x{size:02x})   Peripheral device type: {type_in_string}',
            ' Vendor identification: {t10_vendor_identification}',
            ' Product identification: {product_identification}',
            ' Product revision level: {product_revision_level}',
            ' Unit serial number: {product_serial_number}'
            if item.product_serial_number is not None else ''
        ]
        data.update(self._fill_missing_values(item))
        lines = (line for line in lines if line)
        return '\n'.join(lines).format(
            pqual=device['qualifier'],
            device_type=device['type'],
            size=item.calc_byte_size(),
            type_in_string=SCSI_PERIPHERAL_DEVICE_TYPE[device['type']],
            version_name=SCSI_VERSION_NAME[data['version']],
            product_serial_number=item.product_serial_number,
            resp_data_format=data['response_data_format'],
            **data)

    def _format_0x00_page(self, data, item):
        from infi.asi.cdb.inquiry.vpd_pages import SCSI_PERIPHERAL_DEVICE_TYPE
        lines = [
            ' Only hex output supported. sg_vpd decodes more pages.',
            'VPD INQUIRY, page code=0x00:',
            '   [PQual={peripheral_device_qualifier}  Peripheral device type: {peripheral_device_type}]',
            '   Supported VPD pages:',
        ]
        vpd_string = '     {number}\t{name}'
        lines += [vpd_string.format(number=hex(vpd_page), name=self._get_vpd_page_name(vpd_page, data))
                  for vpd_page in data['vpd_parameters']]
        return '\n'.join(lines).format(
            peripheral_device_type=SCSI_PERIPHERAL_DEVICE_TYPE[data['peripheral_device']['type']],
            peripheral_device_qualifier=data['peripheral_device']['qualifier']
        )

    def _format_0x80_page(self, data, item):
        lines = ['VPD INQUIRY: Unit serial number page',
                 '  Unit serial number: {product_serial_number}']
        return '\n'.join(lines).format(**data)

    def _format_0x83_page(self, data, item):
        from binascii import hexlify
        from infi.asi.cdb.inquiry.vpd_pages import SCSI_DESIGNATOR_TYPES, SCSI_DESIGNATOR_ASSOCIATIONS
        from infi.asi.cdb.inquiry.vpd_pages import SCSI_CODE_SETS

        lines = ['VPD INQUIRY: Device Identification page']
        descriptor_base_string = [
            '  Designation descriptor number {descriptor_number}, descriptor length: {descriptor_length}',
            '    designator_type: {designator_type_string},  code_set: {code_set_string}',
            '    associated with the {association_string}'
        ]
        descriptor_lines = []
        for designator_index, designator in enumerate(data['designators_list']):
            designator_string = self._get_designator_output_string(designator)
            designator_lines = '\n'.join(descriptor_base_string + [designator_string])
            formatted_lines = designator_lines.format(
                descriptor_number=designator_index + 1,
                descriptor_length=item.designators_list[designator_index].byte_size,
                designator_type_string=SCSI_DESIGNATOR_TYPES[designator['designator_type']],
                code_set_string=SCSI_CODE_SETS[designator['code_set']],
                association_string=SCSI_DESIGNATOR_ASSOCIATIONS[designator['association']].lower(),
                packed_string='0x' + hexlify(item.designators_list[designator_index].pack())[8:],
                ieee_company_id=designator.get('ieee_company_id'),
                vendor_specific_identifier=designator.get('vendor_specific_identifier'),
                vendor_specific_identifier_extension=designator.get('vendor_specific_identifier_extension'),
                vendor_specific_identifier_a=designator.get('vendor_specific_identifier_a'),
                vendor_specific_identifier_b=designator.get('vendor_specific_identifier_b'),
                relative_target_port_identifier=designator.get('relative_target_port_identifier'),
                target_port_group=designator.get('target_port_group'),
                logical_group=designator.get('logical_group'),
                md5_logical_identifier=designator.get('md5_logical_identifier'),
                scsi_name_string=designator.get('scsi_name_string'),
                assigned_uuid=designator.get('assigned_uuid'),
            )
            descriptor_lines.append(formatted_lines)
        lines += descriptor_lines
        return '\n'.join(lines).format(**data)

    def format(self, item):
        data = self._to_dict(item)
        page_code = data.get('page_code')
        if page_code in self.SUPPORTED_PAGES:
            format_method = self.SUPPORTED_PAGES[page_code]
            return format_method(data, item)
        # calling super() because we don't handle other pages yet
        return super(InqOutputFormatter, self).format(item)


class ReadkeysOutputFormatter(OutputFormatter):
    def format(self, item):
        lines = ['Reservation keys:']
        if item.key_list is not None:
            for key in item.key_list:
                lines.append('Key: {0}' % hex(key))
        return '\n'.join(lines)

class ReadreservationOutputFormatter(OutputFormatter):
    def format(self, item):
        lines = [
          'Generation: 0x%x' % item.pr_generation,
          'Reservation key: 0x%x' % item.reservation_key,
          'Scope: 0x%x' % item.scope]
        return '\n'.join(lines)

class LunsOutputFormatter(OutputFormatter):

    def format(self, item):
        data = self._to_dict(item)
        return '\n'.join([str(lun) for lun in data['lun_list']])

class RtpgOutputFormatter(DefaultOutputFormatter):

    def _to_dict(self, item):
        item = super(RtpgOutputFormatter, self)._to_dict(item)

        if isinstance(item, int) and item > 2:
            return hex(item)
        return item
