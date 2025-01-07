import smtplib
import pytz
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from time import sleep
from os import path


def prepare_datetime_stamp(functions,time_zone,log):
    utc_stamp = functions.get_date_time({
        "action":"datetime",
        "format": '%H:%M:%S %Y-%m-%d',
    })
    if time_zone != "disable":
        try:
            local_stamp = functions.get_date_time({
                "action":"datetime",
                "format": '%I:%M:%S%p %Y-%m-%d',
                "time_zone": time_zone
            })
        except Exception as e:
            time_zone_str = ", ".join(pytz.all_timezones)
            log.logger.error(f"alerting module -> setting time stamp error skipping [{time_zone}] error [{e}]")
            log.logger.warning(f"alerting module -> available timezones are: [{time_zone_str}]")
            local_stamp = "Disabled"

    return (utc_stamp, local_stamp)


def prepare_alert(alert_profile, comm_obj, profile, env, functions, log):
    log.logger.info("alerting module -> prepare report requested")

    utc_time, local_time = prepare_datetime_stamp(functions, comm_obj["local_time_zone"], log)

    title = False if comm_obj["title"] == None or comm_obj["title"] == "None" else comm_obj["title"]

    body = f"NODECTL {'UP' if alert_profile == 'clear' else 'DOWN'} ALERT\n"
    if title:
        body += f"Title: {title}\n"
    body += f"Cluster: {env}\n"
    body += f"Profile: {profile}\n"
    body += f"\nUTC: {utc_time}\n"
    body += f"{local_time}\n"
    body += "\nAuto Restart action taken\n\n"

    if not isinstance(alert_profile,dict) and alert_profile == "clear":
        body += "ALERT CLEARED - Node is Ready"
    elif not isinstance(alert_profile,dict) and alert_profile == "test":
        body += "ALERT TEST - This is a test only"
    elif not alert_profile[profile]["match"]:
        body += "Alert: Majority Fork detected.\n"
    elif alert_profile[profile]["minority_fork"]:
        body += "Alert: Minority Fork detected.\n"
    elif alert_profile[profile]["consensus_fork"]:
        body += "Alert: Consensus Fork detected.\n"
    elif alert_profile[profile]["action"] == "restart_full":
        body += f"Alert: Node found in [{alert_profile[profile]['node_state']}]\nRestart initiated.\n"
    elif alert_profile[profile]["action"] == "layer0_wait":
        body += "Alert: Node is waiting to join layer0. Layer0 link is not Ready.\n"
    elif alert_profile[profile]["action"] == "layer1_wait":
        body += "Alert: Node is waiting to join layer0. Layer1 link is not Ready.\n"
    elif alert_profile[profile]["action"] == "ep_wait":
        body += "Alert: Unable to access Edge Point from Node.\n"
    else:
        return "skip" # we don't want to send an alert

    if alert_profile == "clear" or alert_profile == "test":
        log.logger.info(f"alerting module -> sending alert [alert {alert_profile}]")
    else:
        log.logger.info(f"alerting module -> sending alert [{alert_profile[profile]['action']}]")
    send_email(comm_obj,body,log)
    return "complete"


def prepare_report(cli, node_service, functions, alert_profile, comm_obj, profile, env, log, direct=False):
    try:
        report_data = cli.get_and_verify_snapshots(530,env,profile)
        cli.node_service = node_service
        nodeid = cli.cli_find(["-p",profile,"-t","self","return_only"])
        dag_addr = cli.cli_nodeid2dag([nodeid,"return_only"])
        full_amount = 0
        reward_items = []
        title = False if comm_obj["title"] == None or comm_obj["title"] == "None" else comm_obj["title"]

        for data in report_data["data"]:
            for reward in data["rewards"]:
                if reward["destination"] == dag_addr:
                    full_amount += reward["amount"]
                    reward_items.append((data["timestamp"],reward["amount"]))

        if direct:
            alert_profile["local_node"] = functions.get_ext_ip()
            alert_profile["node_state"] = alert_profile["state1"]
            
        wallet_balance = functions.pull_node_balance({
            "ip_address": alert_profile["local_node"],
            "wallet": dag_addr.strip(),
            "environment": env
        })

        price = float(wallet_balance["token_price"].replace("$",""))
        full_dag_amount = "{:,.3f}".format(full_amount/1e8)
        full_usd_amount = "$"+"{:,.3f}".format((full_amount/1e8)*price)

        start = report_data["start_time"].strftime('%Y-%m-%d %H:%M:%S')
        end = report_data["end_time"].strftime('%Y-%m-%d %H:%M:%S')

    except Exception as e:
        log.logger.error(f"alerting -> send report failed with [{e}]")
        return # skip report if an error occurred
    
    body = "NODECTL REPORT\n"
    if title:
        body += f"Title: {title}\n"
    body += f"Cluster: {env}\n"
    body += f"Profile: {profile}\n\n"

    body += f"Status: {alert_profile['node_state']}\n\n"

    body += f"Wallet: {dag_addr}\n"
    body += f"Wallet Balance: {wallet_balance['balance_dag']}\n"
    body += f"Wallet Balance: {wallet_balance['balance_usd']}\n"

    body += f"{wallet_balance['token_symbol']} Price: ${price}\n\n"
    body += f"Snapshot History Size [SHZ]: 530\n"
    body += f"start: {start}\n"
    body += f"end: {end}\n"
    body += f"SHZ {wallet_balance['token_symbol']} Earned: {full_dag_amount}\n"
    body += f"SHZ {wallet_balance['token_symbol']} USD: {full_usd_amount}\n\n"

    utc_time, local_time = prepare_datetime_stamp(functions, comm_obj["local_time_zone"], log)
    body += f"UTC: {utc_time}\n"
    body += f"{local_time}\n\n"

    body += "Last 10 Transactions\n"
    body += "====================\n"

    for n, item in enumerate(reward_items):
        body += f"{item[0]}: {item[1]/1e8}\n"
        if n > 10:
            break
        
    body += f"\nEnd Report"
    send_email(comm_obj,body,log)

    log.logger.info("alerting module -> prepare report requested")


def send_email(comm_obj,body,log):
    if comm_obj["send_method"] == "single":
        if len(comm_obj["recipients"]) > 1:
            try:
                for i, recipient in enumerate(comm_obj["recipients"]):
                    if i < 1:
                        send_to = recipient
                        continue
                    send_to += f", {recipient}"
            except:
                log.logger.error(f"alerting module -> unable to figure out recipients to send alert/report to: [{comm_obj['recipients']}]")
                return

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(comm_obj["gmail"], comm_obj["token"])

    for email in comm_obj["recipients"]:
        email = send_to if comm_obj["send_method"] == "single" else email
        msg = MIMEMultipart()
        msg['From'] = comm_obj["gmail"]
        msg['To'] = email
        msg['Subject'] = "Constellation Network"

        msg.attach(MIMEText(body, 'plain'))

        text = msg.as_string()
        log.logger.info(f"alerting module -> email alert/report sent to: [{email}]")
        server.sendmail(comm_obj["gmail"], email, text)
        if comm_obj["send_method"] == "single": 
            break
        sleep(2)
    
    server.quit()




# action:
# ep_wait
# NoActionNeeded
# layer0_wait
# layer1_wait
# restart_full

# match:
# consensus_fork
# minority_fork



