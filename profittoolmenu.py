#!/usr/bin/python3
# -*- coding: utf-8 -*-

import pytvspos as pv
from pytvspos import Account
from pytvspos import Wrapper
import datetime
import time
import sys
import base58
import json

import profittool as pt

class Things():
    def __init__(self, username='nobody'):
        self.username = username
        self.pto = None
    def count_profits(self):
        self.pto = None
        chaintype = "0"
        addr = ""
        fee_rate = -1		
        last_height = 0
        # mainnet or testnet
        while chaintype!="1" and chaintype !="2":
            try:
                chaintype = input("Choose mainnet(1) or testnet(2): ")
            except Exception as e:
                print("Please input (1)mainnet or (2)testnet!");continue
            if chaintype!="1" and chaintype !="2":
        	    print("Please input (1)mainnet or (2)testnet!");continue
        if chaintype=="1":
        	chain = pv.default_chain()
        else:
            chain = pv.testnet_chain()
        print("Chain_name: ", chain.chain_name)
        # address
        isValid = False
        while not isValid:
            try:
                addr = input("Enter address for supernode: ")
            except Exception as e:
                print("Invalid address!");continue
            isValid = (len(addr)==35) and chain.validate_address(addr)
            if not isValid:
        	    print("Invalid address:", addr);continue
        print("Address: ", addr)

        # fee rate
        while fee_rate<0 or fee_rate>1:
            try:
                fee_rate = float(input("Enter fee_rate for supernode: "))
            except Exception as e:
                print("Invalid fee_rate!");continue
            if fee_rate<0 or fee_rate>1:
        	    print("Invalid fee_rate:", fee_rate, "Must between 0 and 1!");continue
        print("Fee_rate: ", fee_rate)

        now_height = chain.height()
        confirmations = 31
        while last_height<=0 or last_height>=now_height-confirmations:
            try:
                last_height = int(input("Enter last profits payment end height: "))
            except Exception as e:
                print("Invalid last_height!");continue
            if last_height<=0 or last_height>=now_height:
        	    print("Invalid last_height:", last_height, "! Must >0 and <", now_height-confirmations, "!");continue
        print("Last Height: ", last_height)
        pto = pt.ProfitTool(chain,addr, fee_rate)
        pto.calculate_profits(last_height, confirmations)
        pto.print_title_data()
        pto.print_leases_data()
        endblk = chain.block(pto.end_height)
        #endblk_time = datetime.datetime.fromtimestamp(endblk['timestamp'] // 1000000000)
        filename = "{0}_{1}.xls".format(pto.address, pto.end_height)
        pto.export_to_excel(filename)
        self.pto = pto

    def load_profits(self):
        self.pto = None
        pto = pt.ProfitTool()
        filename = input("Enter excel filename: ")
        if pto.import_from_excel(filename)<0:
        	print("Open [{0}] failed!".format(filename))
        	return
        pto.print_title_data()
        pto.print_leases_data()
        self.pto = pto

    def pay_profits(self):
        if self.pto == None:
        	print("Profits data is not ready!")
        	return
        isLenEnough = False
        while not isLenEnough:
            try:
                private_key = input("Enter private key for sender: ")
            except Exception as e:
                print("Invalid private key!");continue
            isLenEnough = (len(private_key)>=44)
            if not isLenEnough:
        	    print("Invalid private key:", private_key);continue
        self.pto.pay_profits(private_key)

    def print_profits(self):
        if self.pto == None:
        	print("Profits data is not ready!")
        	return
        self.pto.print_title_data()
        self.pto.print_leases_data()
class Menu():
    def __init__(self):
        self.thing = Things()
        self.choices = {
            "1": self.thing.count_profits,
            "2": self.thing.load_profits,
            "3": self.thing.pay_profits,
            "4": self.thing.print_profits,
            "0": self.quit
        }

    def display_menu(self):
        print("""
Operation Menu:
1. Count profits from chain
2. Load profits data from excel
3. Pay profits
4. Print profits
0. Quit
""")
    def run(self):
        while True:
            self.display_menu()
            try:
                choice = input("Enter an option: ")
            except Exception as e:
                print("Please input a valid option!");continue

            choice = str(choice).strip()
            action = self.choices.get(choice)
            if action:
                action()
            else:
                print("{0} is not a valid choice".format(choice))

    def quit(self):
        print("\nThank you for using Profit Tool!\n")
        sys.exit(0)





# chain = pv.default_chain()
# now_height = chain.height()
# # print("Chain Height:", now_height)

# # blk = chain.block(now_height)

# # now_time = datetime.datetime.fromtimestamp(blk['timestamp'] // 1000000000)
# # print("Now Block:{0} Time: {1}".format(now_height, now_time))

# # #yesterday = now_time - datetime.timedelta(days=1)
# # #print("yesTime: {}".format(yesterday))

# last_height = now_height - 14400 + 1

# # lastblk = chain.block(last_height)

# # lastblk_time = datetime.datetime.fromtimestamp(lastblk['timestamp'] // 1000000000)
# # print("Last Block:{0} Time: {1}".format(last_height, lastblk_time))


# #addr = 'tvEdmTiKDjuYhgKyMQ6pgnUHitBzARx4F3c'
# addr = 'tvGezfk7kMgfv3qoZWzDjnoLV2p1JgFoTiE'

# addr = 'tvK9LthxPHcwMxxacyCH3u6sm3jpvRJFa4q'


# pto = pt.ProfitTool(chain,addr, 0.25)
# pto.calculate_profits(last_height, 0)

# pto.print_title_data()
# pto.print_leases_data()

# filename = 'data.xls'
# pto.export_to_excel(filename)
# pto.import_from_excel(filename)

# pto.print_title_data()
# pto.print_leases_data()
