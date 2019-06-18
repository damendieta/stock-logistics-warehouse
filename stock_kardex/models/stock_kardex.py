# Copyright 2019 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from random import randint

from odoo import _, api, exceptions, fields, models


class StockKardex(models.Model):
    _name = 'stock.kardex'
    _inherit = 'barcodes.barcode_events_mixin'
    _description = 'Stock Kardex'

    name = fields.Char()
    address = fields.Char()
    mode = fields.Selection(
        [('pick', 'Pick'), ('put', 'Put'), ('inventory', 'Inventory')],
        default='pick',
        required=True,
    )
    location_id = fields.Many2one(
        comodel_name='stock.location',
        required=True,
        domain="[('kardex', '=', True)]",
        context="{'default_kardex': True}",
        ondelete='restrict',
        help="The Kardex source location for Pick operations "
        "and destination location for Put operations.",
    )
    current_move_line = fields.Many2one(comodel_name='stock.move.line')

    number_of_ops = fields.Integer(
        compute='_compute_number_of_ops', string='Number of Operations'
    )
    number_of_ops_all = fields.Integer(
        compute='_compute_number_of_ops_all',
        string='Number of Operations in all Kardex',
    )

    operation_descr = fields.Char(
        string="Operation", default="Scan next PID", readonly=True
    )

    # tray information (will come from stock.location or a new tray model)
    kardex_tray_x = fields.Integer(
        string='X', compute='_compute_kardex_tray_matrix'
    )
    kardex_tray_y = fields.Integer(
        string='Y', compute='_compute_kardex_tray_matrix'
    )
    kardex_tray_matrix = fields.Serialized(
        compute='_compute_kardex_tray_matrix'
    )

    # current operation information
    picking_id = fields.Many2one(
        related='current_move_line.picking_id', readonly=True
    )
    product_id = fields.Many2one(
        related='current_move_line.product_id', readonly=True
    )
    product_uom_id = fields.Many2one(
        related='current_move_line.product_uom_id', readonly=True
    )
    product_uom_qty = fields.Float(
        related='current_move_line.product_uom_qty', readonly=True
    )
    qty_done = fields.Float(
        related='current_move_line.qty_done', readonly=True
    )
    lot_id = fields.Many2one(related='current_move_line.lot_id', readonly=True)

    _barcode_scanned = fields.Char(
        "Barcode Scanned",
        help="Value of the last barcode scanned.",
        store=False,
    )

    def on_barcode_scanned(self, barcode):
        raise exceptions.UserError('Scanned barcode: {}'.format(barcode))

    @api.depends()
    def _compute_number_of_ops(self):
        for record in self:
            record.number_of_ops = record.count_move_lines_to_do()

    @api.depends()
    def _compute_number_of_ops_all(self):
        for record in self:
            record.number_of_ops_all = record.count_move_lines_to_do_all()

    @api.depends()
    def _compute_kardex_tray_matrix(self):
        for record in self:
            # prototype code, random matrix
            cols = randint(4, 8)
            rows = randint(1, 3)
            selected = [randint(0, cols - 1), randint(0, rows - 1)]
            cells = []
            for __ in range(rows):
                row = []
                for __ in range(cols):
                    row.append(randint(0, 1))
                cells.append(row)

            record.kardex_tray_x = selected[0] + 1
            record.kardex_tray_y = selected[1] + 1
            record.kardex_tray_matrix = {
                # x, y: position of the selected cell
                'selected': selected,
                # 0 is empty, 1 is not
                'cells': cells,
            }

    def _domain_move_lines_to_do(self):
        domain = [
            # TODO check state
            ('state', '=', 'assigned')
        ]
        domain_extensions = {
            'pick': [('location_id', 'child_of', self.location_id.id)],
            'put': [('location_dest_id', 'child_of', self.location_id.id)],
            # TODO
            'inventory': [('id', '=', 0)],
        }
        return domain + domain_extensions[self.mode]

    def _domain_move_lines_to_do_all(self):
        domain = [
            # TODO check state
            ('state', '=', 'assigned')
        ]
        kardex_locations = self.env['stock.location'].search(
            [('kardex', '=', True)]
        )
        domain_extensions = {
            'pick': [('location_id', 'child_of', kardex_locations.ids)],
            'put': [('location_dest_id', 'child_of', kardex_locations.ids)],
            # TODO
            'inventory': [('id', '=', 0)],
        }
        return domain + domain_extensions[self.mode]

    def count_move_lines_to_do(self):
        self.ensure_one()
        return self.env['stock.move.line'].search_count(
            self._domain_move_lines_to_do()
        )

    def count_move_lines_to_do_all(self):
        self.ensure_one()
        return self.env['stock.move.line'].search_count(
            self._domain_move_lines_to_do_all()
        )

    def button_release(self):
        raise exceptions.UserError(_('what does this one do?'))

    def process_current_pick(self):
        # test code, TODO the smart one
        # (scan of barcode increments qty, save calls action_done?)
        line = self.current_move_line
        line.qty_done = line.product_qty
        line.move_id._action_done()

    def process_current_put(self):
        raise exceptions.UserError(_('Put workflow not implemented'))

    def process_current_inventory(self):
        raise exceptions.UserError(_('Inventory workflow not implemented'))

    def button_save(self):
        self.ensure_one()
        method = 'process_current_{}'.format(self.mode)
        getattr(self, method)()
        self.select_next_move_line()
        if not self.current_move_line:
            # sorry not sorry
            return {
                'effect': {
                    'fadeout': 'slow',
                    'message': _('Congrats, you cleared the queue!'),
                    'img_url': '/web/static/src/img/smile.svg',
                    'type': 'rainbow_man',
                }
            }

    # TODO call this each time we process a move line
    def select_next_move_line(self):
        self.ensure_one()
        # TODO sort?
        next_move_line = self.env['stock.move.line'].search(
            self._domain_move_lines_to_do(), limit=1
        )
        self.current_move_line = next_move_line

    def action_open_screen(self):
        self.select_next_move_line()
        self.ensure_one()
        screen_xmlid = 'stock_kardex.stock_kardex_view_form_screen'
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'views': [[self.env.ref(screen_xmlid).id, 'form']],
            'res_id': self.id,
            'target': 'fullscreen',
            'flags': {
                'headless': True,
                'form_view_initial_mode': 'edit',
                'no_breadcrumbs': True,
            },
        }

    def action_menu(self):
        menu_xmlid = 'stock_kardex.stock_kardex_form_menu'
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.kardex',
            'views': [[self.env.ref(menu_xmlid).id, 'form']],
            'name': _('Menu'),
            'target': 'new',
            'res_id': self.id,
        }

    # TODO: should the mode be changed on all the kardex at the same time?
    def switch_pick(self):
        self.mode = 'pick'

    def switch_put(self):
        self.mode = 'put'

    def switch_inventory(self):
        self.mode = 'inventory'
