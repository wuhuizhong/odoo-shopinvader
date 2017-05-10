# -*- coding: utf-8 -*-
# Copyright 2017 Akretion (http://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import api, fields, models
from openerp import SUPERUSER_ID


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    shopinvader_bind_ids = fields.One2many(
        'shopinvader.product',
        'record_id',
        string='Shopinvader Binding')

    @api.multi
    def unlink(self):
        for record in self:
            # TODO we should propose to redirect the old url
            record.shopinvader_bind_ids.unlink()
        return super(ProductTemplate, self).unlink()


class ShopinvaderProduct(models.Model):
    _name = 'shopinvader.product'
    _inherit = ['locomotive.binding', 'abstract.url']
    _inherits = {'product.template': 'record_id'}

    record_id = fields.Many2one(
        'product.template',
        required=True,
        ondelete='cascade')
    lang_id = fields.Many2one(
        'res.lang',
        'Lang',
        required=True)
    seo_title = fields.Char()
    meta_description = fields.Char()
    meta_keywords = fields.Char()

    _sql_constraints = [
        ('record_uniq', 'unique(backend_id, record_id)',
         'A product can only have one binding by backend.'),
    ]

    @api.multi
    def create_index_binding(self):
        self.ensure_one()
        nosql_backend = self.backend_id.nosql_backend_id
        if nosql_backend:
            model = self.env['ir.model'].search(
                [('model', '=', 'nosql.product.product')])
            index = self.env['nosql.index'].search([
                ('lang_id', '=', self.lang_id.id),
                ('backend_id', '=', self.backend_id.id),
                ('model_id', '=', model.id)])
            for variant in self.product_variant_ids:
                self.env['nosql.product.product'].create({
                    'record_id': variant.id,
                    'backend_id': nosql_backend.id,
                    'locomotive_product_id': self.id,
                    'index_id': index.id})

    @api.model
    def create(self, vals):
        binding = super(LocomotiveProduct, self).create(vals)
        binding.create_index_binding()
        return binding

    @api.depends('url_builder', 'record_id.name')
    def _compute_url(self):
        return super(LocomotiveProduct, self)._compute_url()

    @api.onchange('backend_id')
    def set_default_lang(self):
        self.ensure_one()
        langs = self.backend_id.lang_ids
        if langs:
            self.lang_id = langs[0]
            return {'domain': {'lang_id': [('id', 'in', langs.ids)]}}


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _get_untaxed_price(self, price):
        if self._uid == SUPERUSER_ID and self._context.get('company_id'):
            taxes = self.taxes_id.filtered(
                lambda r: r.company_id.id == self._context['company_id'])
        else:
            taxes = self.taxes_id
        return self.env['account.tax']._fix_tax_included_price(
            price, taxes, [])

    def _get_rounded_price(self, pricelist, qty, tax_included):
        price = pricelist.price_get(self.id, qty, None)[pricelist.id]
        if not tax_included:
            price = self._get_untaxed_price(price)
        return pricelist.currency_id.round(price)

    def _get_pricelist_dict(self, pricelist, tax_included):
        def get_all_parent(categ):
            if categ:
                return [categ.id] + get_all_parent(categ.parent_id)
            else:
                return []
        self.ensure_one()
        res = []
        categ_ids = get_all_parent(self.categ_id)
        items = self.env['product.pricelist.item'].search([
            '|', '|',
            ('product_id', '=', self.id),
            ('product_tmpl_id', '=', self.product_tmpl_id.id),
            ('categ_id', 'in', categ_ids),
            ])
        item_qty = set([item.min_quantity
                        for item in items if item.min_quantity > 1] + [1])
        last_price = None
        for qty in item_qty:
            price = self._get_rounded_price(pricelist, qty, tax_included)
            if price != last_price:
                res.append({
                    'qty': qty,
                    'price': price,
                    })
                last_price = price
        return res


class ProductFilter(models.Model):
    _name = 'product.filter'
    _description = 'Product Filter'

    field_id = fields.Many2one(
        'ir.model.fields',
        'Field',
        domain=[('model', 'in', (
            'product.template',
            'product.product',
            'locomotive.product',
            ))])
    help = fields.Html(translate=True)
    name = fields.Char(translate=True, required=True)


class NosqlProductProduct(models.Model):
    _inherit = 'nosql.product.product'
    _inherits = {'locomotive.product': 'locomotive_product_id'}

    locomotive_product_id = fields.Many2one(
        'locomotive.product',
        required=True,
        ondelete='cascade')

    # TODO some field are related to the template
    # stock_state
    # images
    # from price / best discount

    categs = fields.Many2many(
        comodel_name='shopinvader.category',
        compute='_compute_categ',
        string='Shopinvader Categories')

    images = fields.Serialized(
        compute='_compute_image',
        string='Shopinvader Image')

    def _get_categories(self):
        self.ensure_one()
        return self.categ_id

    def _compute_categ(self):
        for record in self:
            shop_categs = []
            for categ in record._get_categories():
                # TODO filtrer les categ qui sont du backend
                for loco_categ in categ.locomotive_bind_ids:
                    if loco_categ.backend_id\
                            == record.locomotive_product_id.backend_id:
                        shop_categs.append(loco_categ.id)
                        break
            record.categs = shop_categs

    def _compute_image(self):
        for record in self:
            images = []
            # TODO get image from public storage
            record.images = images