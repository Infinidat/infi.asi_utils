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
