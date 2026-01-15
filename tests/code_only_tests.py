import pytest,dataclasses
import liquidityhelper
from liquidityhelper import should_close_channel
import datetime
from classes import BitcartInvoice
import common_functions
def test_BitcartInvoice():
    # test paid invoice LN
    invoice={'buyer_email': 'myemail@gmail.com', 'created': 'date', 'currency': 'USD', 'discount': None, 'exception_status': 'none', 'expiration': 15, 'expiration_seconds': 900, 'id': '01K9XFECPZ8DR605PQ59YZX4ZX', 'metadata': {}, 'notes': '', 'notification_url': 'https://getbarebits.com/wc-api/WC_Gateway_Bitcart/', 'order_id': '123829', 'paid_currency': 'BTC (⚡)', 'paid_date': '2026-11-13T02:07:32.048009Z', 'payment_id': '01K9XFED0FXGF3Q9GG87D01F02', 'payment_methods': ['01K9EHX06Q6R2HVWNZE6M0GXY6'], 'payments': [{'amount': '0.00000196', 'confirmations': 0, 'contract': '', 'created': '2025-11-13T02:06:52.432513Z', 'currency': 'btc', 'discount': None, 'divisibility': 8, 'hint': '', 'id': '01K9XFECY93EHAN3G55ZBFKTJ1', 'invoice_id': '01K9XFECPZ8DR605PQ59YZX4ZX', 'is_used': False, 'label': '', 'lightning': False, 'lookup_field': 'e1d9d0cf05', 'metadata': {}, 'name': 'BTC', 'node_id': None, 'payment_address': 'bc1gggggggggggggggggggggggggggggggggg', 'payment_url': 'bitcoin:bc1gggggggggggggggggggggggggggggggggg?amount=0.00000196&time=1762999612&exp=900', 'rate': '102040.82', 'rate_str': '$102,040.82 (USD)', 'recommended_fee': 1.48, 'rhash': None, 'symbol': 'btc', 'updated': None, 'user_address': None, 'wallet_id': '01K9EHX06Q6R2HVWNZE6M0GXY6'}, {'amount': '0.00000196', 'confirmations': 0, 'contract': '', 'created': 'date', 'currency': 'btc', 'discount': None, 'divisibility': 8, 'hint': '', 'id': '01K9XFED0FXGF3Q9GG87D01F02', 'invoice_id': '01K9XFECPZ8DR605PQ59YZX4ZX', 'is_used': True, 'label': '', 'lightning': True, 'lookup_field': '07813ef93cd3200e952b7def3e01de0b3a526be03b27c95cb00812d95057cad0', 'metadata': {}, 'name': 'BTC (⚡)', 'node_id': 'g6e7775777', 'payment_address': 'lnbcgdfgdd', 'payment_url': 'lnbcv', 'rate': '102040.82', 'rate_str': '$102,040.82 (USD)', 'recommended_fee': 0.0, 'rhash': '07813ef93cd3200e952b7def3e01de0b3a526be03b27c95cb00812d95057cad0', 'symbol': 'btc', 'updated': 'date', 'user_address': None, 'wallet_id': '01K9EHX06Q6R2HVWNZE6M0GXY6'}], 'price': '0.20', 'product_names': {}, 'product_quantities': {}, 'products': [], 'promocode': '', 'redirect_url': 'https://getbarebits.com/checkout/order-received/123829/?key=wc_order_I74fD5stnJwvO', 'refund_id': None, 'sent_amount': 1.96e-06, 'shipping_address': '', 'status': 'complete', 'store_id': '01K9EKQP06WP5YM8HESVZAF7TV', 'time_left': 0, 'tx_hashes': ['07813ef93cd3200e952b7def3e01de0b3a526be03b27c95cb00812d95057cad0'], 'updated': '2025-11-13T02:07:32.056737Z', 'user_id': '01K9AEBNFM1D3AH0MAZ7W7GESK'}
    field_names = set(f.name for f in dataclasses.fields(BitcartInvoice))
    classified_invoice = BitcartInvoice(**{k: v for k, v in invoice.items() if k in field_names})
    assert classified_invoice.is_paid()

    # test unpaid invoice
    invoice={'buyer_email': 'myemail@gmail.com', 'created': 'date', 'currency': 'USD', 'discount': None, 'exception_status': 'none', 'expiration': 15, 'expiration_seconds': 900, 'id': '01K9XEPJE7T7EBVCKHSRAVBAB7', 'metadata': {}, 'notes': '', 'notification_url': 'https://getbarebits.com/wc-api/WC_Gateway_Bitcart/', 'order_id': '123828', 'paid_currency': None, 'paid_date': None, 'payment_id': None, 'payment_methods': ['01K9EHX06Q6R2HVWNZE6M0GXY6'], 'payments': [{'amount': '0.00000098', 'confirmations': 0, 'contract': '', 'created': '2025-11-13T01:53:51.743138Z', 'currency': 'btc', 'discount': None, 'divisibility': 8, 'hint': '', 'id': '01K9XEPJK1ZSNQV5YJW36ZECWY', 'invoice_id': '01K9XEPJE7T7EBVCKHSRAVBAB7', 'is_used': False, 'label': '', 'lightning': False, 'lookup_field': '0befc12e03', 'metadata': {}, 'name': 'BTC', 'node_id': None, 'payment_address': 'bc1q95079gjws30yp4qvf08ej68z2fk65cafmxx79u', 'payment_url': 'bitcoin:bc1q95079gjws30yp4qvf08ej68z2fk65cafmxx79u?amount=0.00000098&time=1762998831&exp=900', 'rate': '102040.82', 'rate_str': '$102,040.82 (USD)', 'recommended_fee': 1.48, 'rhash': None, 'symbol': 'btc', 'updated': None, 'user_address': None, 'wallet_id': '01K9EHX06Q6R2HVWNZE6M0GXY6'}, {'amount': '0.00000098', 'confirmations': 0, 'contract': '', 'created': '2025-11-13T01:53:51.743146Z', 'currency': 'btc', 'discount': None, 'divisibility': 8, 'hint': '', 'id': '01K9XEPJKY6ZYF893NTWGFC9Q2', 'invoice_id': '01K9XEPJE7T7EBVCKHSRAVBAB7', 'is_used': False, 'label': '', 'lightning': True, 'lookup_field': '598238', 'metadata': {}, 'name': 'BTC (⚡)', 'node_id': 'g6e7775777', 'payment_address': 'lnbc980n1p532w395', 'payment_url': 'lnbc985', 'rate': '102040.82', 'rate_str': '$102,040.82 (USD)', 'recommended_fee': 0.0, 'rhash': '598224b9fe8891d2937edfee23072285fd6fcc48f796f39a1f7e0aac56d32738', 'symbol': 'btc', 'updated': None, 'user_address': None, 'wallet_id': '01K9EHX06Q6R2HVWNZE6M0GXY6'}], 'price': '0.10', 'product_names': {}, 'product_quantities': {}, 'products': [], 'promocode': '', 'redirect_url': 'https://getbarebits.com/checkout/order-received/123828/?key=wc_order_YJc8gx1kvdohp', 'refund_id': None, 'sent_amount': 0.0, 'shipping_address': '', 'status': 'expired', 'store_id': '01K9EKQP06WP5YM8HESVZAF7TV', 'time_left': 0, 'tx_hashes': [], 'updated': '2025-11-13T02:08:51.658522Z', 'user_id': '01K9AEBNFM1D3AH0MAZ7W7GESK'}
    field_names = set(f.name for f in dataclasses.fields(BitcartInvoice))
    classified_invoice = BitcartInvoice(**{k: v for k, v in invoice.items() if k in field_names})
    assert not classified_invoice.is_paid()

    # test paid invoice onchain
    invoice={'buyer_email': '', 'created': 'date', 'currency': 'BTC', 'discount': None, 'exception_status': 'none', 'expiration': 2628000, 'expiration_seconds': 157680000, 'id': '01K9EXG0Z7GDY6J25G4FYNS1QG', 'metadata': {}, 'notes': 'topupbarebits', 'notification_url': '', 'order_id': 'order_20251107_102349', 'paid_currency': 'BTC', 'paid_date': '2025-11-07T11:54:26.182404Z', 'payment_id': '01K9EXG10EJWM39S1TK2MYWHY2', 'payment_methods': ['01K9EHX06Q6R2HVWNZE6M0GXY6'], 'payments': [{'amount': '0.00100000', 'confirmations': 0, 'contract': '', 'created': '2025-11-07T10:23:49.279161Z', 'currency': 'btc', 'discount': None, 'divisibility': 8, 'hint': '', 'id': '01K9EXG10EJWM39S1TK2MYWHY2', 'invoice_id': '01K9EXG0Z7GDY6J25G4FYNS1QG', 'is_used': True, 'label': '', 'lightning': False, 'lookup_field': '049a84de2b', 'metadata': {}, 'name': 'BTC', 'node_id': None, 'payment_address': 'bc1q82sg26j36z68q0t6lm2zpr40dd4qj3yeemfa49', 'payment_url': 'bitcoin:bc1q82sg26j36z68q0t6lm2zpr40dd4qj3yeemfa49?amount=0.001&time=1762511029&exp=157680000', 'rate': '1.00000000', 'rate_str': '1.00000000 BTC', 'recommended_fee': 2.94, 'rhash': None, 'symbol': 'btc', 'updated': 'date', 'user_address': None, 'wallet_id': '01K9EHX06Q6R2HVWNZE6M0GXY6'}, {'amount': '0.00100000', 'confirmations': 0, 'contract': '', 'created': 'date', 'currency': 'btc', 'discount': None, 'divisibility': 8, 'hint': '', 'id': '01K9EXG10YJNP60X856CDGSQ7R', 'invoice_id': '01K9EXG0Z7GDY6J25G4FYNS1QG', 'is_used': False, 'label': '', 'lightning': True, 'lookup_field': 'd2a36a7', 'metadata': {}, 'name': 'BTC (⚡)', 'node_id': 'g6e7775777', 'payment_address': 'lnbcj', 'payment_url': 'lnbc164j', 'rate': '1.00000000', 'rate_str': '1.00000000 BTC', 'recommended_fee': 0.0, 'rhash': 'd2a36ab5eb132ea5deb02f3f1b1fd96c7031f4c4323015e74b0d4edea1e44917', 'symbol': 'btc', 'updated': None, 'user_address': None, 'wallet_id': '01K9EHX06Q6R2HVWNZE6M0GXY6'}], 'price': '0.00100000', 'product_names': {}, 'product_quantities': {}, 'products': [], 'promocode': '', 'redirect_url': '', 'refund_id': None, 'sent_amount': 0.001, 'shipping_address': '', 'status': 'complete', 'store_id': '01K9EKQP06WP5YM8HESVZAF7TV', 'time_left': 155381852, 'tx_hashes': ['8787e7f294ff39855e5d96f7673b19e7a11ea1d11c4742fa3f7137b482fccd52'], 'updated': '2025-11-08T13:54:22.275261Z', 'user_id': '01K9AEBNFM1D3AH0MAZ7W7GESK'}
    field_names = set(f.name for f in dataclasses.fields(BitcartInvoice))
    classified_invoice = BitcartInvoice(**{k: v for k, v in invoice.items() if k in field_names})
    assert classified_invoice.is_paid()

    # test bb topup invoice

    invoice = {'buyer_email': 'office@getbarebits.com', 'created': 'date', 'currency': 'USD', 'discount': None, 'exception_status': 'none', 'expiration': 15, 'expiration_seconds': 900, 'id': '01K9XFECPZ8DR605PQ59YZX4ZX', 'metadata': {}, 'notes': 'topupbarebits', 'notification_url': 'https://getbarebits.com/wc-api/WC_Gateway_Bitcart/', 'order_id': '123829', 'paid_currency': 'BTC (⚡)', 'paid_date': '2025-11-13T02:07:32.048009Z', 'payment_id': '01K9XFED0FXGF3Q9GG87D01F02', 'payment_methods': ['01K9EHX06Q6R2HVWNZE6M0GXY6'], 'payments': [{'amount': '0.00000196', 'confirmations': 0, 'contract': '', 'created': '2025-11-13T02:06:52.432513Z', 'currency': 'btc', 'discount': None, 'divisibility': 8, 'hint': '', 'id': '01K9XFECY93EHAN3G55ZBFKTJ1', 'invoice_id': '01K9XFECPZ8DR605PQ59YZX4ZX', 'is_used': False, 'label': '', 'lightning': False, 'lookup_field': 'e1d9d0cf05', 'metadata': {}, 'name': 'BTC', 'node_id': None, 'payment_address': 'bc666666', 'payment_url': 'bitcoin:gg5ddy?amount=0.00000196&time=1762999612&exp=900', 'rate': '102040.82', 'rate_str': '$102,040.82 (USD)', 'recommended_fee': 1.48, 'rhash': None, 'symbol': 'btc', 'updated': None, 'user_address': None, 'wallet_id': '01K9EHX06Q6R2HVWNZE6M0GXY6'}, {'amount': '0.00000196', 'confirmations': 0, 'contract': '', 'created': 'date', 'currency': 'btc', 'discount': None, 'divisibility': 8, 'hint': '', 'id': '01K9XFED0FXGF3Q9GG87D01F02', 'invoice_id': '01K9XFECPZ8DR605PQ59YZX4ZX', 'is_used': True, 'label': '', 'lightning': True, 'lookup_field': 'yyyryr', 'metadata': {}, 'name': 'BTC (⚡)', 'node_id': 'yryryry', 'payment_address': 'ryryy', 'payment_url': 'ryryry', 'rate': '102040.82', 'rate_str': '$102,040.82 (USD)', 'recommended_fee': 0.0, 'rhash': 'ytryy', 'symbol': 'btc', 'updated': '2025-11-13T02:07:32.065484Z', 'user_address': None, 'wallet_id': 'ryrtry'}], 'price': '0.20', 'product_names': {}, 'product_quantities': {}, 'products': [], 'promocode': '', 'redirect_url': 'https://getbarebits.com/checkout/order-received/123829/?key=wc_order_I74fD5stnJwvO', 'refund_id': None, 'sent_amount': 1.96e-06, 'shipping_address': '', 'status': 'complete', 'store_id': 'ryry', 'time_left': 0, 'tx_hashes': ['ryry'], 'updated': '2025-11-13T02:07:32.056737Z', 'user_id': 'ryy'}
    field_names = set(f.name for f in dataclasses.fields(BitcartInvoice))
    classified_invoice = BitcartInvoice(**{k: v for k, v in invoice.items() if k in field_names})
    assert classified_invoice.is_bb_topup_invoice()

    # test topup invoice
    invoice = {'buyer_email': 'office@getbarebits.com', 'created': '2date',
               'currency': 'USD', 'discount': None, 'exception_status': 'none', 'expiration': 15,
               'expiration_seconds': 900, 'id': '01K9XFECPZ8DR605PQ59YZX4ZX', 'metadata': {}, 'notes': 'topupself',
               'notification_url': 'https://getbarebits.com/wc-api/WC_Gateway_Bitcart/', 'order_id': '123829',
               'paid_currency': 'BTC (⚡)', 'paid_date': 'date',
               'payment_id': '01K9XFED0FXGF3Q9GG87D01F02', 'payment_methods': ['01K9EHX06Q6R2HVWNZE6M0GXY6'],
               'payments': [{'amount': '0.00000166', 'confirmations': 0, 'contract': '',
                             'created': '2date', 'currency': 'btc', 'discount': None,
                             'divisibility': 8, 'hint': '', 'id': '01K9XFECY93EHAN3G55ZBFKTJ1',
                             'invoice_id': '01K9XFECPZ8DR605PQ59YZX4ZX', 'is_used': False, 'label': '',
                             'lightning': False, 'lookup_field': 'e1d9d0cf05', 'metadata': {}, 'name': 'BTC',
                             'node_id': None, 'payment_address': 'bc1gggggggggggggggggggggggggggggggggg',
                             'payment_url': 'bitcoin:bc1gggggggggggggggggggggggggggggggggg?amount=0.000001776&time=1762999612&exp=900',
                             'rate': '102040.82', 'rate_str': '$102,040.82 (USD)', 'recommended_fee': 1.48,
                             'rhash': None, 'symbol': 'btc', 'updated': None, 'user_address': None,
                             'wallet_id': '01K9EHX06Q6R2HVWNZE6M0GXY6'},
                            {'amount': '0.00000146', 'confirmations': 0, 'contract': '',
                             'created': '20date', 'currency': 'btc', 'discount': None,
                             'divisibility': 8, 'hint': '', 'id': '01K9XFED0FXGF3Q9GG87D01F02',
                             'invoice_id': '01K9XFECPZ8DR605PQ59YZX4ZX', 'is_used': True, 'label': '',
                             'lightning': True,
                             'lookup_field': 'ghgfhhfh',
                             'metadata': {}, 'name': 'BTC (⚡)',
                             'node_id': 'g6e7775777',
                             'payment_address': 'lnbcv',
                             'payment_url': 'lnbcdv',
                             'rate': '102040.82', 'rate_str': '$102,040.82 (USD)', 'recommended_fee': 0.0,
                             'rhash': 'fhghgh',
                             'symbol': 'btc', 'updated': '2dateZ', 'user_address': None,
                             'wallet_id': '01K9EHX06Q6R2HVWNZE6M0GXY6'}], 'price': '0.20', 'product_names': {},
               'product_quantities': {}, 'products': [], 'promocode': '',
               'redirect_url': 'https://getbarebits.com/checkout/order-received/123829/?key=wc_order_I74fD5stnJwvO',
               'refund_id': None, 'sent_amount': 1.96e-06, 'shipping_address': '', 'status': 'complete',
               'store_id': '01K9EKQP06WP5YM8HESVZAF7TV', 'time_left': 0,
               'tx_hashes': ['07813ef93cd3200e952b7def3e01de0b3a526be03b27c95cb00812d95057cad0'],
               'updated': '2date', 'user_id': '01K9AEBNFM1D3AH0MAZ7W7GESK'}
    field_names = set(f.name for f in dataclasses.fields(BitcartInvoice))
    classified_invoice = BitcartInvoice(**{k: v for k, v in invoice.items() if k in field_names})
    assert classified_invoice.is_self_topup_invoice()

    # test non-topup invoice
    invoice = {'buyer_email': 'office@getbarebits.com', 'created': '20dateZ',
               'currency': 'USD', 'discount': None, 'exception_status': 'none', 'expiration': 15,
               'expiration_seconds': 900, 'id': '01K9XFECPZ8DR605PQ59YZX4ZX', 'metadata': {}, 'notes': '',
               'notification_url': 'https://getbarebits.com/wc-api/WC_Gateway_Bitcart/', 'order_id': '123829',
               'paid_currency': 'BTC (⚡)', 'paid_date': '20dateZ',
               'payment_id': '01K9XFED0FXGF3Q9GG87D01F02', 'payment_methods': ['01K9EHX06Q6R2HVWNZE6M0GXY6'],
               'payments': [{'amount': '0.00000196', 'confirmations': 0, 'contract': '',
                             'created': '20dateZ', 'currency': 'btc', 'discount': None,
                             'divisibility': 8, 'hint': '', 'id': '01K9XFECY93EHAN3G55ZBFKTJ1',
                             'invoice_id': '01K9XFECPZ8DR605PQ59YZX4ZX', 'is_used': False, 'label': '',
                             'lightning': False, 'lookup_field': 'e1d9d0cf05', 'metadata': {}, 'name': 'BTC',
                             'node_id': None, 'payment_address': 'bc1gggggggggggggggggggggggggggggggggg',
                             'payment_url': 'bitcoin:bc1gggggggggggggggggggggggggggggggggg?amount=0.00000196&time=1762999612&exp=900',
                             'rate': '102040.82', 'rate_str': '$102,040.82 (USD)', 'recommended_fee': 1.48,
                             'rhash': None, 'symbol': 'btc', 'updated': None, 'user_address': None,
                             'wallet_id': '01K9EHX06Q6R2HVWNZE6M0GXY6'},
                            {'amount': '0.00000196', 'confirmations': 0, 'contract': '',
                             'created': '20date', 'currency': 'btc', 'discount': None,
                             'divisibility': 8, 'hint': '', 'id': '01K9XFED0FXGF3Q9GG87D01F02',
                             'invoice_id': '01K9XFECPZ8DR605PQ59YZX4ZX', 'is_used': True, 'label': '',
                             'lightning': True,
                             'lookup_field': '07813ef93cd30',
                             'metadata': {}, 'name': 'BTC (⚡)',
                             'node_id': 'g6e7775777',
                             'payment_address': 'lnbcdv',
                             'payment_url': 'lnbc19dv',
                             'rate': '102040.82', 'rate_str': '$102,040.82 (USD)', 'recommended_fee': 0.0,
                             'rhash': '07813ef93cd3200e952b7def3e01de0b3a526be03b27c95cb00812d95057cad0',
                             'symbol': 'btc', 'updated': '2025-date', 'user_address': None,
                             'wallet_id': '01K9EHX06Q6R2HVWNZE6M0GXY6'}], 'price': '0.20', 'product_names': {},
               'product_quantities': {}, 'products': [], 'promocode': '',
               'redirect_url': 'https://getbarebits.com/checkout/order-received/123829/?key=wc_order_I74fD5stnJwvO',
               'refund_id': None, 'sent_amount': 1.96e-06, 'shipping_address': '', 'status': 'complete',
               'store_id': '01K9EKQP06WP5YM8HESVZAF7TV', 'time_left': 0,
               'tx_hashes': ['07813ef93cd3200e952b7def3e01de0b3a526be03b27c95cb00812d95057cad0'],
               'updated': '20dateZ', 'user_id': '01K9AEBNFM1D3AH0MAZ7W7GESK'}
    field_names = set(f.name for f in dataclasses.fields(BitcartInvoice))
    classified_invoice = BitcartInvoice(**{k: v for k, v in invoice.items() if k in field_names})
    assert not classified_invoice.is_self_topup_invoice()
    assert not classified_invoice.is_bb_topup_invoice()

def test_should_close_channel():
    # test if local > threshold
    local_balance=1
    remote_balance=0
    local_threshold=0
    remote_threshold=0
    assert should_close_channel(local_balance,remote_balance,local_threshold,remote_threshold)
    # test if remote < threshold
    local_balance = 0
    remote_balance = 0
    local_threshold = 0
    remote_threshold = 1
    assert should_close_channel(local_balance, remote_balance, local_threshold, remote_threshold)
    # test if zero remote
    local_balance = 1
    remote_balance = 0
    local_threshold = 2
    remote_threshold = 0
    assert should_close_channel(local_balance, remote_balance, local_threshold, remote_threshold)

def test_distribute_sats_over_channels():

    sats=1
    answer=common_functions.distribute_sats_over_channels(sats=sats,channels=1)
    assert answer==[1]
    assert sum(answer)==sats

    sats = 2
    answer = common_functions.distribute_sats_over_channels(sats=sats, channels=1)
    assert answer==[2]
    assert sum(answer) == sats

    sats = 300
    answer = common_functions.distribute_sats_over_channels(sats=sats, channels=2)
    assert answer == [150,150]
    assert sum(answer) == sats

    sats = 303
    answer = common_functions.distribute_sats_over_channels(sats=sats, channels=2)
    assert answer == [151, 152]
    assert sum(answer) == sats

    sats = 304
    answer = common_functions.distribute_sats_over_channels(sats=sats, channels=3)
    assert answer == [101, 101,102]
    assert sum(answer) == sats