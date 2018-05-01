from infi.instruct.struct import Struct, Field, FieldListContainer, AnonymousField
from infi.instruct.buffer import Buffer
from infi.asi.sense.asc import AdditionalSenseCode
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

    SUPPORTED_PAGES = {0x0: [' Only hex output supported. sg_vpd decodes more pages.',
                            'VPD INQUIRY, page code=0x00:',
                            '   [PQual={peripheral_device[qualifier]}  Peripheral device type: {peripheral_device_type}]',
                            '   Supported VPD pages:',
                            ],
                       0x80: ['VPD INQUIRY: Unit serial number page',
                              '  Unit serial number: {product_serial_number}'
                             ],
                       0x83: ['VPD INQUIRY: Device Identification page',]
                       }

    def format(self, item):
        from infi.asi.cdb.inquiry.vpd_pages import SCSI_PERIPHERAL_DEVICE_TYPE, SCSI_VPD_NAME, SCSI_CODE_SETS, \
        SCSI_DESIGNATOR_TYPES, SCSI_DESIGNATOR_ASSOCIATIONS, SCSI_DESIGNATOR_TYPE_OUTPUT
        data = self._to_dict(item)
        if data['page_code'] == 0x00:
            vpd_string = '      {number} {name}'
            vpd_lines = []
            for vpd_page in data['vpd_parameters']:
                if vpd_page in range(0xb0, 0xc0):  # 0xb0 to 0xbf are per peripheral device type
                    page_name = SCSI_VPD_NAME.get(vpd_page, {}).get(data['peripheral_device']['type'], '')
                else:
                    page_name = SCSI_VPD_NAME.get(vpd_page, '')
                vpd_dictionary = {'number': hex(vpd_page), 'name': page_name}
                vpd_lines.append(vpd_string.format(**vpd_dictionary))
            self.SUPPORTED_PAGES[data['page_code']] += vpd_lines
            data['peripheral_device_type'] = SCSI_PERIPHERAL_DEVICE_TYPE[data['peripheral_device']['type']]
        elif data['page_code'] == 0x80:
            pass  # nothing to do here...
        elif data['page_code'] == 0x83:
            descriptor_base_string = '''   Designation descriptor number {descriptor_number}, descriptor length: {descriptor_length}
    designator_type: {designator_type_string},  code_set: {code_set_string}
    associated with the {association_string}'''
            descriptor_designators_lines = []
            for designator_index, designator in enumerate(data['designators_list']):
                designator.update({k+'_hex' if type(v) is int else k: hex(v) if type(v) is int else v for k,v in designator.items()})
                designator['descriptor_number'] = designator_index + 1
                designator['descriptor_length'] = item.designators_list[designator_index].byte_size
                designator['code_set_string'] = SCSI_CODE_SETS[designator['code_set']]
                designator['association_string'] = SCSI_DESIGNATOR_ASSOCIATIONS[designator['association']].lower()
                designator['designator_type_string'] = SCSI_DESIGNATOR_TYPES[designator['designator_type']]
                designator_string = SCSI_DESIGNATOR_TYPE_OUTPUT[designator['designator_type']]
                if designator['designator_type'] == 3:  # NAA has more then 1 possible output
                    designator_string = SCSI_DESIGNATOR_TYPE_OUTPUT[designator['designator_type']][designator['naa']]
                    designator['hex_packed_string'] = '0x'+''.join(['%02x' % by for by in item.designators_list[designator_index].pack()[4:]])
                descriptor_designators_lines.append('\n'.join([descriptor_base_string, designator_string]).format(**designator))
            self.SUPPORTED_PAGES[data['page_code']] += descriptor_designators_lines
        else:  # calling super() because we can't handle other pages yet
            return super(InqOutputFormatter, self).format(item)
        return '\n'.join(self.SUPPORTED_PAGES[data['page_code']]).format(**data)

class ReadkeysOutputFormatter(OutputFormatter):
    def format(self, item):
        lines = ['Reservation keys:']
        if item.key_list != None:
            for key in item.key_list:
                lines.append('Key: {0}' % hex(key))
        return '\n'.join(lines)

class ReadreservationOutputFormatter(OutputFormatter):
    def format(self, item):
        lines = [ \
          'Generation: 0x%x' % item.pr_generation, \
          'Reservation key: 0x%x' % item.reservation_key, \
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
