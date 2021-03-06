#!/usr/bin/python
# -*- coding:utf-8 _*- 
"""
@author:TXU
@file:run
@time:2022/06/25
@email:tao.xu2008@outlook.com
@description: tpRunner command exec entrance
"""

import argparse
import atexit

import subprocess
from loguru import logger

import config
from utils import util
from api_runner.run_api import api_runner_exec
from applications.base_app.models import TestReport


def pytest_parser():
    """pytest args parser"""
    parser = argparse.ArgumentParser(add_help=False)
    pytest_group = parser.add_argument_group("--runner pytest 's arguments")
    pytest_group.add_argument("--repeat-scope", action="store", dest="repeat_scope", default="session",
                              choices=['function', 'class', 'module', 'session'],
                              help="pytest-repeat,default:session")
    pytest_group.add_argument("--seconds", action="store", dest="seconds", default=0, type=int,
                              help="pytest-stress:Loop tests for user-defined time(seconds), default:0 --TODO")
    pytest_group.add_argument("--html", action="store", dest="html_path", default=None,
                              help="html path,default:None,will use the same as log path")
    pytest_group.add_argument("--junit-xml", action="store", dest="junit_xml_path", default=None,
                              help="junit-xml path,default:None,will use the same as log path")
    return parser


def runner_parser_args():
    """
    Set runner argument
    :return:
    """

    # Parent parser
    parser = argparse.ArgumentParser(description='Test Platform Runner', parents=[pytest_parser()])
    parser.set_defaults(project_name='project_name')
    parser.set_defaults(env_name='env_name')
    parser.set_defaults(build_type='build_type')

    # Sub parser
    action = parser.add_subparsers(dest='api | web', required=True, help='specify the test runner')

    # api
    from api_runner.argument import set_api_runner_subparsers
    set_api_runner_subparsers(action)

    # web
    from web_runner.argument import set_web_runner_subparsers
    set_web_runner_subparsers(action)

    return parser.parse_args()


def _init_test_session(args):
    """
    ???????????????session???????????????DB
    :param args:
    :return:
    """
    logger.info("???????????????session??????...")
    # ????????????
    project_name = args.project_name
    env_name = args.env_name
    config.set_global_value("env_name", env_name)
    config.set_global_value("project_name", project_name)

    logger.info("??????api_test_report?????????...")

    report = TestReport.objects.create(
        **{
            "create_time": config.TIME_STR,
            "build_type": args.build_type,
            # "env_id": 1
        }
    )
    report_id = report.id

    # ????????????session??????
    session_attr = config.TestSession(project_name, env_name, report_id)

    report.log_path = session_attr.log_path
    report.save()

    return session_attr


def _generate_allure_report(test_session):
    """
    ??????????????????????????????????????????????????????allure?????????
    ????????????????????????Jenkins??????allure??????
    ???????????????allure serve??????????????????allure??????
    :param test_session:
    :return:
    """
    try:
        logger.info("generate allure report...")
        xml_report_path = test_session.xml_report_path
        if util.get_net_mac_address() == '00:16:3e:17:7c:40':
            # 47.99.145.123 ???????????????
            if not test_session.report_id:
                logger.error("?????????????????????????????????????????????")
                return

            from tpRunner.commons.jenkins_opt import JenkinsOperation
            # ?????????????????????????????????
            jenkins_conf = config.global_cf.get_kvs('JENKINS')
            job_name = jenkins_conf.get('job_name')
            token = jenkins_conf.get('token')
            jenkins_opt = JenkinsOperation(
                url=jenkins_conf.get('url'),
                user=jenkins_conf.get('user'),
                password=jenkins_conf.get('password'),
            )
            parameters = {
                'xml_report_path': xml_report_path
            }
            logger.info(xml_report_path)
            # ??????jenkins?????????build number???????????????
            build_number = jenkins_opt.get_next_build_number(job_name)
            number = jenkins_opt.trigger_build_job(job_name, parameters, token)
            logger.info(number)
            # allure_url = jenkins_opt.get_build_allure_url(job_name, build_number)
            # ??????jenkins job/build?????????????????????????????????????????????
            TestReport.objects.filter(id__exact=test_session.report_id).update(
                client='47.99.145.123',
                jenkins_job_name='test-platform-report',
                jenkins_build_number=build_number,
                # allure_url=allure_url
            )
        else:
            # ????????????
            allure_serve_cmd = 'D:\\allure-2.16.1\\bin\\allure serve {}'.format(xml_report_path)
            logger.info(allure_serve_cmd)
            subprocess.Popen(allure_serve_cmd, shell=True, close_fds=True)
            # p.wait()
    except Exception as e:
        logger.error(e)


def run_pytest_with_logger(args):
    """
    pytest + logger
    :param args:
    :return:
    """
    # ?????????????????????session - ?????????????????????
    try:
        test_session = _init_test_session(args)
    except Exception as e:
        raise e

    handler_id = None
    try:
        # - ??????logger??????????????????
        # ????????????logger????????????pytest???????????????????????????pytest?????????????????????????????????log_path????????????????????????logger
        handler_id = logger.add(
            test_session.log_path,
            rotation='100 MB',
            retention='7 days',
            enqueue=True,
            encoding="utf-8",
            level=test_session.log_level
        )
        atexit.register(logger.remove)

        # - ????????????
        return api_runner_exec(test_session, args)
    except Exception as e:
        raise e
    finally:
        logger.info("test log: {}".format(test_session.log_path))
        logger.info("result data: {}".format(test_session.xml_report_path))
        try:
            logger.remove(handler_id)
        except Exception as e:
            logger.error(e)
        reports = TestReport.objects.filter(id=test_session.report_id)
        if reports.count() > 0:
            report = reports.first()
            # 0?????????????????? - ??????; ?????????????????????
            if report.step_total == 0:
                # ???????????????????????????????????? - ??????
                report.status = False
                report.build_status = 'build-status-static'
                report.duration = 1
                report.save()
            else:
                # ????????????
                _generate_allure_report(test_session)


if __name__ == '__main__':
    runner_args = runner_parser_args()
    return_code = run_pytest_with_logger(runner_args)
    exit(return_code)
