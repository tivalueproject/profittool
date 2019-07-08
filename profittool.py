from pytvspos import is_offline
from pytvspos import Account
import pytvspos
import time
import datetime
import struct
import json
import base58
import logging
import xlwt
import xlrd

class ProfitTool(object):
    def __init__(self, chain=pytvspos.default_chain(), address='', fee_rate=0):
        self.chain = chain
        self.wrapper = chain.api_wrapper
        self.address = address
        self.fee_rate = fee_rate
        self.titles = ['chain_name', 'address', 'start_height', 'end_height', 'minting_total', 'fee_rate', 'minting_average_balance', 'available_balance', 'leases_total', 'leases_ratio', 'amount_to_pay']
        self.headers = ['lease_id', 'address', 'lease_height', 'amount', 'amount_to_pay']

    def calculate_minting_total(self, start_height, end_height):
        self.start_height = start_height
        self.end_height = end_height
        self.minting_total = 0

        # must be ready before call this function.
        now_height = self.chain.height()

        if not self.address:
            raise InvalidAddressException("No address")
        elif start_height <= 0:
            msg = 'start height must be > 0'
            pytvspos.throw_error(msg, InvalidParameterException)
        elif end_height > now_height:
            msg = 'end height must be <= now_height' % self.now_height
            pytvspos.throw_error(msg, InvalidParameterException)
        else:
            print('calculating', start_height, '==>', end_height)
            begin = start_height
            REQSIZE = 100
            while begin+REQSIZE <= end_height:
                self.minting_total += self.calculate_minting(begin, begin+REQSIZE-1)
                begin += REQSIZE
            self.minting_total += self.calculate_minting(begin, end_height)

            print(self.start_height, "==>", self.end_height, "minting_total:", self.minting_total)    


    def calculate_minting(self, begin_height, end_height):
        resp = self.wrapper.request('/blocks/seq/%s/%s' % (begin_height, end_height))
        minting = 0
        for blkidx in range(len(resp)):
            blk = resp[blkidx]
            if blk['generator']!=self.address:
               continue;
            txs = blk['transactions']
            for txidx in range(len(txs)):
                tx = txs[txidx]
                if tx['type'] == 5:
                    #print(tx)
                    #print(tx['currentBlockHeight'],":", tx['recipient'], "+", tx['amount'], "(minting reward)")
                    minting += tx['amount']
        print(begin_height, "-->", end_height, "minting:", minting, end='\r')
        return minting


    def fetch_leases_to_pay(self, last_height):
        if is_offline():
            pytvspos.throw_error("Cannot fetch leases_to_pay in offline mode.", NetworkException)
        try:
            resp = self.wrapper.request('/transactions/activeLeaseList/%s' % self.address)
            logging.debug(resp)
            #print(resp[0])
        except Exception as ex:
            msg = "Failed to get activeLeaseList. ({})".format(ex)
            pytvspos.throw_error(msg, NetworkException)
        self.leases_to_pay = []
        self.leases_total = 0
        for leaseidx in range(len(resp[0])):
            lease = resp[0][leaseidx]
            if lease['recipient']==self.address and lease['type']==3 and lease['height']<last_height:
                lease_to_pay = {}
                address = self.chain.public_key_to_address(base58.b58decode(lease['proofs'][0]['publicKey']))
                lease_to_pay['lease_id'] = lease['id']
                lease_to_pay['address'] = address
                lease_to_pay['lease_height'] = lease['height']
                lease_to_pay['amount'] = lease['amount']
                self.leases_to_pay.append(lease_to_pay)
                self.leases_total += lease_to_pay['amount']
        #print("======================================")
        #print(self.leases_to_pay)

    def fetch_minting_average_balance(self):
        if is_offline():
            pytvspos.throw_error("Cannot fetch minting_average_balance in offline mode.", NetworkException)
            return 0
        try:
            resp = self.wrapper.request('/addresses/balance/details/%s' % self.address)
            logging.debug(resp)
            #print(resp)
            self.minting_average_balance = resp['mintingAverage']
            self.available_balance = resp['available']
            #print(self.minting_average_balance)
            return None
        except Exception as ex:
            msg = "Failed to get minting average balance. ({})".format(ex)
            pytvspos.throw_error(msg, NetworkException)
            return 0

    def calculate_amount_to_pay(self):
        if self.leases_total<=0:
            return
        self.amount_to_pay_total = (self.leases_total / (self.available_balance + self.leases_total)) * self.minting_total * (1-self.fee_rate)

        for leaseidx in range(len(self.leases_to_pay)):
            lease = self.leases_to_pay[leaseidx]
            #print("(", lease['amount'], "/", self.minting_average_balance, ")",  "*", self.minting_total, "* ( 1 - ", self.fee_rate, ")")
            amount_to_pay = int((lease['amount'] / self.leases_total) * self.amount_to_pay_total)
            #print(lease['address'], amount_to_pay)
            lease['amount_to_pay'] = amount_to_pay
        #print(self.leases_to_pay)

    def calculate_profits(self, last_height, confirmations):
        start_height = last_height+1
        now_height = self.chain.height()
        print("Chain Height:", now_height)
        blk = self.chain.block(now_height)
        now_time = datetime.datetime.fromtimestamp(blk['timestamp'] // 1000000000)
        print("Now Block:{0} Time: {1}".format(now_height, now_time))
        lastblk = self.chain.block(last_height)
        lastblk_time = datetime.datetime.fromtimestamp(lastblk['timestamp'] // 1000000000)
        print("Last Block:{0} Time: {1}".format(last_height, lastblk_time))
        self.fetch_minting_average_balance()
        self.fetch_leases_to_pay(start_height)
        self.calculate_minting_total(start_height, now_height - confirmations)
        self.calculate_amount_to_pay()

    def pay_profits(self, sender_private_key):
        pay_failed_list = []
        pay_sent_list = []
        sender = Account(chain=self.chain, private_key=sender_private_key)
        for lease_to_pay in self.leases_to_pay:
            recipient = Account(chain=self.chain, address=lease_to_pay['address'])
            try:
                resp = sender.send_payment(recipient, amount=lease_to_pay['amount_to_pay'], attachment='PROFITS://{0}|{1}|{2}'.format(lease_to_pay['lease_id'], self.start_height, self.end_height))
                print(resp)

            except Exception as ex:
                msg = "Pay profits to {0} Failed! ({1})".format(recipient.address, ex)
                print(msg)
                pay_failed_list.append(lease_to_pay)
                continue
            # add to paylist
            pay_sent = {}
            pay_sent['txid'] = resp['id']
            pay_sent['lease_id'] = lease_to_pay['lease_id']
            pay_sent_list.append(pay_sent)

        if len(pay_failed_list)==0:
            print("All profits payment transactions sent.")
        else:
            filename = "{0}_{1}_payfailed.xls".format(self.address, self.end_height)
            print("Some of profits paid faild. Check [{}] for details.".format(filename))
            self.export_to_excel(filename, pay_failed_list)

        if len(pay_sent_list)>0:
            filename = "{0}_{1}_pay_sent.xls".format(self.address, self.end_height)
            print("Check [{}] for sent transactions' hashes.".format(filename))
            self.export_sent_transactions(filename, pay_sent_list)

    def export_sent_transactions(self, filename, sent_list):
        workbook = xlwt.Workbook(encoding = 'ascii')
        sheet = workbook.add_sheet('profits_sent')

        # header
        titlestyle = xlwt.XFStyle()
        titlepattern = xlwt.Pattern() 
        titlepattern.pattern = xlwt.Pattern.SOLID_PATTERN
        titlepattern.pattern_fore_colour = 23
        titlestyle.pattern = titlepattern

        titlefont = xlwt.Font()
        titlefont.name = 'Times New Roman' 
        titlefont.bold = True
        titlestyle.font = titlefont

        contentstyle = xlwt.XFStyle()
        contentpattern = xlwt.Pattern()
        contentpattern.pattern = xlwt.Pattern.SOLID_PATTERN
        contentpattern.pattern_fore_colour = 22
        contentstyle.pattern = contentpattern

        sheet.col(0).width = 13000
        sheet.col(1).width = 10000
        sheet.col(2).width = 3500
        sheet.col(3).width = 3500
        sheet.col(4).width = 3500
        sheet.col(5).width = 2000
        sheet.col(6).width = 6000
        sheet.col(7).width = 4000
        sheet.col(8).width = 4000
        sheet.col(9).width = 4000
        sheet.col(10).width = 4000

        # set title line
        i = 0
        for k in self.titles:
            sheet.write(0, i, k, titlestyle)
            i = i + 1
        sheet.write(1, 0, self.chain.chain_name, contentstyle)
        sheet.write(1, 1, self.address, contentstyle) 
        sheet.write(1, 2, self.start_height, contentstyle) 
        sheet.write(1, 3, self.end_height, contentstyle) 
        sheet.write(1, 4, self.minting_total, contentstyle) 
        sheet.write(1, 5, self.fee_rate, contentstyle) 
        sheet.write(1, 6, self.minting_average_balance, contentstyle) 
        sheet.write(1, 7, self.available_balance, contentstyle) 
        sheet.write(1, 8, self.leases_total, contentstyle) 
        sheet.write(1, 9, xlwt.Formula('=I2/(H2+I2)', contentstyle))
        sheet.write(1, 10, xlwt.Formula('=E2*J2*(1-F2)', contentstyle))

        # set headers
        sheet.write(2, 0, 'lease_id', titlestyle) 
        sheet.write(2, 1, "txid", titlestyle)

        # set content
        row = 3
        for pay_sent in sent_list:
            sheet.write(row, 0, pay_sent['lease_id'], contentstyle) 
            sheet.write(row, 1, pay_sent['txid'], contentstyle) 
            row = row + 1
        workbook.save(filename)
        print("Transactions' hashes data saved into [{0}].".format(filename))

    def export_to_excel(self, filename, lease_list=[]):
        workbook = xlwt.Workbook(encoding = 'ascii')
        sheet = workbook.add_sheet('profits')

        titlestyle = xlwt.XFStyle()
        titlepattern = xlwt.Pattern() 
        titlepattern.pattern = xlwt.Pattern.SOLID_PATTERN
        titlepattern.pattern_fore_colour = 23
        titlestyle.pattern = titlepattern

        titlefont = xlwt.Font()
        titlefont.name = 'Times New Roman' 
        titlefont.bold = True
        titlestyle.font = titlefont


        contentstyle = xlwt.XFStyle()
        contentpattern = xlwt.Pattern()
        contentpattern.pattern = xlwt.Pattern.SOLID_PATTERN
        contentpattern.pattern_fore_colour = 22
        contentstyle.pattern = contentpattern

        footstyle = xlwt.XFStyle()
        footpattern = xlwt.Pattern() 
        footfont = xlwt.Font()
        footfont.bold = True
        footstyle.font = footfont
        footstyle.pattern = contentpattern


        sheet.col(0).width = 13000
        sheet.col(1).width = 10000
        sheet.col(2).width = 3500
        sheet.col(3).width = 3500
        sheet.col(4).width = 3500
        sheet.col(5).width = 2000
        sheet.col(6).width = 6000
        sheet.col(7).width = 4000
        sheet.col(8).width = 4000
        sheet.col(9).width = 4000
        sheet.col(10).width = 4000

        # set title line
        i = 0
        for k in self.titles:
            sheet.write(0, i, k, titlestyle)
            i = i + 1
        sheet.write(1, 0, self.chain.chain_name, contentstyle)
        sheet.write(1, 1, self.address, contentstyle) 
        sheet.write(1, 2, self.start_height, contentstyle) 
        sheet.write(1, 3, self.end_height, contentstyle) 
        sheet.write(1, 4, self.minting_total, contentstyle) 
        sheet.write(1, 5, self.fee_rate, contentstyle) 
        sheet.write(1, 6, self.minting_average_balance, contentstyle) 
        sheet.write(1, 7, self.available_balance, contentstyle) 
        sheet.write(1, 8, self.leases_total, contentstyle) 
        sheet.write(1, 9, xlwt.Formula('I2/(H2+I2)'), contentstyle)
        sheet.write(1, 10, xlwt.Formula('E2*J2*(1-F2)'), contentstyle)

        # set headers
        i = 0
        for k in self.headers:
            sheet.write(2, i, k, titlestyle)
            i = i + 1

        
        # set content
        if len(lease_list)>0:
            leases_to_pay = lease_list
        else:
            leases_to_pay = self.leases_to_pay
        start_row = 3
        row = start_row
        for lease_to_pay in leases_to_pay:
            sheet.write(row, 0, lease_to_pay['lease_id'], contentstyle) 
            sheet.write(row, 1, lease_to_pay['address'], contentstyle) 
            sheet.write(row, 2, lease_to_pay['lease_height'], contentstyle) 
            sheet.write(row, 3, lease_to_pay['amount'], contentstyle) 
            sheet.write(row, 4, lease_to_pay['amount_to_pay'], contentstyle) 
            row = row + 1
        sheet.write(row, 0, 'total', footstyle)
        sheet.write(row, 1, '', footstyle)
        sheet.write(row, 2, '', footstyle)
        if row>start_row:
            sheet.write(row, 3, xlwt.Formula('SUM(D{0}:D{1})'.format(start_row+1, row)), footstyle)
            sheet.write(row, 4, xlwt.Formula('SUM(E{0}:E{1})'.format(start_row+1, row)), footstyle)
        else:
            sheet.write(row, 3, 0, footstyle)
            sheet.write(row, 4, 0, footstyle)
        workbook.save(filename)

        print("Profits data saved into [{0}].".format(filename))

    def import_from_excel(self,filename):
        try:
            file = xlrd.open_workbook(filename)
        except Exception as ex:
            msg = "Failed to open file{0}. ({1})!".format(filename,ex)
            return -1
        if file.nsheets==0:
            return -1
        table = file.sheets()[0]
        if not self.check_excel(table):
            return -1
        rows = table.nrows
        
        chain_name = table.cell(1,0).value

        if chain_name == pytvspos.DEFAULT_CHAIN:
            self.chain=pytvspos.default_chain()            
        elif chain_name == pytvspos.TESTNET_CHAIN:
            self.chain=pytvspos.testnet_chain()
        else:
            self.chain.chain_name = 'custom'

        self.address = table.cell(1,1).value
        self.start_height = int(table.cell(1,2).value)
        self.end_height = int(table.cell(1,3).value)
        self.minting_total = int(table.cell(1,4).value)
        self.fee_rate = table.cell(1,5).value
        self.minting_average_balance = int(table.cell(1,6).value)
        self.available_balance = int(table.cell(1,7).value)
        self.leases_total = int(table.cell(1,8).value)

        self.leases_to_pay = []
        for r in range(3,rows-1):
            lease_to_pay = {}
            for h in range(len(self.headers)):
                value = table.cell(r,h).value
                if isinstance(value,float):
                    value = int(value)
                lease_to_pay[self.headers[h]] = value
            self.leases_to_pay.append(lease_to_pay)
        #print(self.leases_to_pay)
        print("Profits data loaded from [{0}] successfully.".format(filename))
        return 0

    def check_excel(self,table):
        rows = table.nrows
        cols = table.ncols
        if cols<len(self.titles) or cols<len(self.headers) or rows<4:
            return False
        title_headers = table.row_values(0)
        #print(title_headers)
        for i in range(len(self.titles)):
            if title_headers[i]!=self.titles[i]:
                return False

        chain_name = table.cell(1,0).value
        if chain_name!=pytvspos.DEFAULT_CHAIN and chain_name!=pytvspos.TESTNET_CHAIN:
            return False
        headers = table.row_values(2)
        #print(headers)
        for i in range(len(self.headers)):
            if headers[i]!=self.headers[i]:
                return False
        return True


    def print_title_data(self):
        print('====================================')
        print('chain_name:\t\t{0}'.format(self.chain.chain_name))
        print('address:\t\t{0}'.format(self.address))
        print('start_height:\t\t{0}'.format(self.start_height))
        print('end_height:\t\t{0}'.format(self.end_height))
        print('minting_total:\t\t{0}'.format(self.minting_total))
        print('fee_rate:\t\t{0}'.format(self.fee_rate))
        print('minting_average_balance:\t\t{0}'.format(self.minting_average_balance))
        print('available_balance:\t\t{0}'.format(self.available_balance))
        print('leases_total:\t\t{0}'.format(self.leases_total))
        print('====================================')
    def print_leases_data(self):
        print('address\t\t\t\t\tlease_height\tamount\tamount_to_pay')
        total_amount = 0
        total_amount_to_pay = 0
        for lease_to_pay in self.leases_to_pay:
            print('{0}\t{1}\t{2}\t{3}'.format(lease_to_pay['address'],lease_to_pay['lease_height'],lease_to_pay['amount'],lease_to_pay['amount_to_pay']) )
            total_amount +=lease_to_pay['amount']
            total_amount_to_pay +=lease_to_pay['amount_to_pay']
        print('------------------------------------')
        print('{0}\t{1}\t{2}\t{3}'.format('total\t\t\t\t', '', total_amount,total_amount_to_pay))


