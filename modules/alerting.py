import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from time import sleep
from os import path


def prepare_alert(alert_profile, comm_obj, profile, env, log):
    log.logger.info("alerting module -> prepare report requested")

    body = "NODECTL ALERT\n"
    body += f"Cluster: {env}\n"
    body += f"Profile: {profile}\n"
    body += "\nAuto Restart action taken\n\n"

    if not isinstance(alert_profile,dict) and alert_profile == "clear":
        body += "ALERT CLEARED - Node is Ready"
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
        
    log.logger.info(f"alerting module -> sending alert [{body}]")
    send_email(comm_obj,body,log)
    return "complete"


def prepare_report(cli, node_service, functions, alert_profile, comm_obj, profile, env, log):
    try:
        report_data = cli.get_and_verify_snapshots(530,env,profile)
        cli.node_service = node_service
        nodeid = cli.cli_find(["-p",profile,"-t","self","return_only"])
        dag_addr = cli.cli_nodeid2dag([nodeid,"return_only"])
        full_amount = 0
        reward_items = []

        for data in report_data["data"]:
            for reward in data["rewards"]:
                if reward["destination"] == dag_addr:
                    full_amount += reward["amount"]
                    reward_items.append((data["timestamp"],reward["amount"]))

        wallet_balance = functions.pull_node_balance({
            "ip_address": alert_profile["local_node"],
            "wallet": nodeid.strip(),
            "environment": env
        })

        price = float(wallet_balance["token_price"].replace("$",""))
        full_dag_amount = "{:,.3f}".format(full_amount/1e8)
        full_usd_amount = "$"+"{:,.3f}".format((full_amount/1e8)*price)

        start = report_data["start_time"].strftime('%Y-%m-%d %H:%M:%S')
        end = report_data["end_time"].strftime('%Y-%m-%d %H:%M:%S')

    except:
        return # skip report if an error occurred
    
    body = "NODECTL REPORT\n"
    body += f"Cluster: {env}\n"
    body += f"Profile: {profile}\n\n"

    body += f"Status: {alert_profile['node_state']}\n\n"

    body += f"Wallet: {dag_addr}\n"
    body += f"Wallet Balance: {wallet_balance['balance_dag']}\n"
    body += f"DAG Price: ${price}\n\n"
    body += f"Snapshot History Size [HHZ]: 530\n"
    body += f"start: {start}\n"
    body += f"end: {end}\n"
    body += f"SHZ $DAG Earned: {full_dag_amount}\n"
    body += f"SHZ $DAG USD: {full_usd_amount}\n\n"

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
        log.logger.info(f"alerting module -> email alert/report sent : [{msg}] to: [{email}]")
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



