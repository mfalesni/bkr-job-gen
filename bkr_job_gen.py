#!/usr/bin/env python2

# It's not the prettiest, it's not the best, but it works
# Milan Falesnik <mfalesni@redhat.com>

import json
import re
import sys
from xml.etree.cElementTree import Element, ElementTree
from StringIO import StringIO
import subprocess
import shlex
import pkg_resources
import sys
import bkr_job_gen
import os
import os.path
from StringIO import StringIO
from random import random
from lxml import etree

# XML SUBMITTER

class RuntimeErrorException(Exception):
    pass

class InvalidXMLException(Exception):
    pass

class BeakerInterface(object):
    def __init__(self, user, password):
        self.credentials = (user, password)
        
    def __run(self, cmd):
        if isinstance(cmd, str):
            cmd = shlex.split(cmd)
        p_open = subprocess.Popen(cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT)
        (stdout, stderr) = p_open.communicate()
        if p_open.returncode != 0:
            print stdout
            raise RuntimeErrorException()
        return stdout

    def setCredentials(self, user, password):
        self.credentials = (user, password)

    def jobSubmit(self, jobxmlfile):
        result = self.__run("bkr job-submit %s" % (jobxmlfile))
        result = result.split(":", 1)[-1].strip()
        result = eval(result)
        result = [int(x.rsplit(":", 1)[-1]) for x in result]
        return result

    def jobGet(self, jobid):
        string = StringIO(self.__run("bkr job-results J:%d" % jobid))
        return etree.parse(string)

    def jobTasks(self, jobid):
        tree = self.jobGet(jobid)
        return tree.xpath("//task")

    def tasksDiffer(self, old, new):
        tests = zip(old, new)
        for test in tests:
            if test[0][1] != test[1][1] or test[0][2] != test[1][2]:
                return True
        return False

    def printTasks(self, tasks):
        longest = 0
        for task in tasks:
            if len(task[0]) > longest:
                longest = len(task[0])
        print "%s%s%s" % ("Task name:".rjust(longest), "Status:".rjust(10), "Result:".rjust(10))
        for i in range(longest + 10 + 10):
            print "~",
        print ""
        fmtstr = "%%%ds%%10s%%10s" % longest
        for task in tasks:
            print fmtstr % (task[0].rjust(longest), task[1].rjust(10), task[2].rjust(10))

    def formatTasks(self, xmltasks):
        return [(xmltask.get("name"), xmltask.get("status"), xmltask.get("result")) for xmltask in xmltasks]

    def isClosure(self, tasks, closure):
        for task in tasks:
            if task[0] == closure:
                if task[1] == "Running":
                    return True
        return False

    def isCancelled(self, tasks):
        for task in tasks:
            if task[1] == "Cancelled":
                return True
        return False

    def monitorTasks(self, jobid, closure="/distribution/reservesys"):
        tasks = self.formatTasks(self.jobTasks(jobid))
        while not self.isClosure(tasks, closure) and not self.isCancelled(tasks):
            newtasks = self.formatTasks(self.jobTasks(jobid))
            if self.tasksDiffer(tasks, newtasks):
                self.printTasks(newtasks)
                tasks = newtasks
        if self.isCancelled(tasks):
            return False
        else:
            return True

class Application(object):
    def random(self):
        return int(random()*10000)

    def tmpFileName(self):
        prefix = self.__class__.__name__
        name = "/tmp/%s" % prefix
        while os.path.exists(name):
            name = "/tmp/%s-%d" % (prefix, self.random())
        return name


class BeakerJobSubmitApplication(Application):
    def __init__(self, name, password, xml, closure):
        print "Username: %s" % name
        print "Password: %s" % password
        assert xml != None
        xmlfile = self.tmpFileName()
        f = open(xmlfile, "w")
        f.write(xml.xmlRepresentation())
        f.close()
        ifc = BeakerInterface(name, password)
        jobs = ifc.jobSubmit(xmlfile)
        os.unlink(xmlfile)
        #TODO: More jobs simultaneously
        return ifc.monitorTasks(jobs[0], closure)

# XML GENERATOR

class UnknownHostRequirementException(Exception):
    def __init__(self, req):
        self.req = req

    def __repr__(self):
        return str(self.req)

class UnknownOperatorException(Exception):
    def __init__(self, req):
        self.req = req

class UnknownPanicException(Exception):
    def __init__(self, req):
        self.req = req

class UnknownPickException(Exception):
    def __init__(self, req):
        self.req = req

class UnknownPriorityException(Exception):
    def __init__(self, req):
        self.req = req

class BeakerBaseObject(object):
    def setValue(self, key, value):
        if key in self.__dict__:
            self.__dict__[key] = value
        else:
            raise KeyError()

    def __str__(self):
        return str(self.__dict__)


class BeakerRecipeTask(BeakerBaseObject):
    """ This class represents one task for Beaker job """

    def __init__(self, name):
        self.name = name
        self.role = "STANDALONE"
        self.params = []

    def addParam(self, name, value):
        self.params.append(BeakerRecipeTaskParam(name, value))

    def toXMLNode(self):
        task = Element("task")
        task.set("name", self.name)
        task.set("role", self.role)
        params = Element("params")
        for param in self.params:
            params.append(param.toXMLNode())
        task.append(params)
        return task

class BeakerRecipeTaskParam(BeakerBaseObject):
    """ This class represents one parameter for Beaker task """

    def __init__(self, name, value):
        self.name = name
        self.value = value

    def toXMLNode(self):
        param = Element("param")
        param.set("name", self.name)
        param.set("value", self.value)
        return param

class BeakerAnd(BeakerBaseObject):
    """ Makes <and> tag """

    def __init__(self, child_nodes=[]):
        self.child_nodes = child_nodes

    def addRequirement(self, requirement):
        if type(requirement) == list:
            self.child_nodes.extend(requirement)
        else:
            self.child_nodes.append(requirement)

    def toXMLNode(self):
        and_element = Element("and")
        for child in self.child_nodes:
            and_element.append(child.toXMLNode())
        return and_element

class BeakerOr(BeakerBaseObject):
    """ Makes <or> tag """

    def __init__(self, child_nodes=[]):
        self.child_nodes = child_nodes

    def addRequirement(self, requirement):
        if type(requirement) == list:
            self.child_nodes.extend(requirement)
        else:
            self.child_nodes.append(requirement)

    def toXMLNode(self):
        or_element = Element("or")
        for child in self.child_nodes:
            or_element.append(child.toXMLNode())
        return or_element

class BeakerRecipeHostRequirement(BeakerBaseObject):
    """ Does child tags inside <hostRequires> tag """
    allowedReqs = ["hostname", "host", "hostlabcontroller", "system_type", "system", "memory", "cpu_count", "numa_node_count", "arch", "auto_prov", "hypervisor", "device"]
    allowedOps = ["=", "<", ">", "<=", ">=", None]
    reOp = re.compile("^[<>=]+")
    def __init__(self, requirement, value):
        self.setReq(requirement, value)

    def setReq(self, requirement, value):
        if requirement not in self.allowedReqs:
            raise UnknownHostRequirementException(requirement)
        self.req = requirement
        findOp = self.reOp.search(value)
        if findOp == None:
            self.operator = findOp
            self.value = value
        else:
            self.operator = value[findOp.start():findOp.end()]
            self.value = value[findOp.end():]
        if self.operator not in self.allowedOps:
            raise UnknownOperatorException(self.operator)

    def toXMLNode(self):
        requirement = Element(self.req)
        if self.operator != None:
            requirement.set("op", self.operator)
        requirement.set("value", self.value)
        return requirement

class BeakerRecipeDistroRequirement(BeakerBaseObject):
    """ Does child tags inside <distroRequires> tag """
    allowedReqs = ["distro", "distro_family", "distro_name", "distro_tag", "distro_variant", "distro_arch", "distro_virt", "distro_method", "distrolabcontroller"]
    allowedOps = ["=", "<", ">", "<=", ">=", None]
    reOp = re.compile("^[<>=]+")
    def __init__(self, requirement, value):
        self.setReq(requirement, value)
        
    def setReq(self, requirement, value):
        if not requirement.startswith("distro_"):
            requirement = "distro_%s" % requirement
        elif not requirement.startswith("distro"):
            requirement = "distro%s" % requirement
        if requirement not in self.allowedReqs:
            raise UnknownHostRequirementException(requirement)
        self.req = requirement
        findOp = self.reOp.search(value)
        if findOp == None:
            self.operator = findOp
            self.value = value
        else:
            self.operator = value[findOp.start():findOp.end()]
            self.value = value[findOp.end():]
        if self.operator not in self.allowedOps:
            raise UnknownOperatorException(self.operator)
 
    def toXMLNode(self):
        requirement = Element(self.req)
        if self.operator != None:
            requirement.set("op", self.operator)
        requirement.set("value", self.value)
        return requirement

class BeakerRecipeHostRequires(BeakerBaseObject):
    """ <hostRequires> """

    def __init__(self, child_nodes=[]):
        self.child_nodes = []

    def addRequirement(self, requirement):
        if type(requirement) == list:
            self.child_nodes.extend(requirement)
        else:
            self.child_nodes.append(requirement)

    def toXMLNode(self):
        requires = Element("hostRequires")
        for child in self.child_nodes:
            requires.append(child.toXMLNode())
        return requires

class BeakerRecipeDistroRequires(BeakerBaseObject):
    """ <distroRequires> """

    def __init__(self, child_nodes=[]):
        self.child_nodes = []

    def addRequirement(self, requirement):
        if type(requirement) == list:
            self.child_nodes.extend(requirement)
        else:
            self.child_nodes.append(requirement)

    def toXMLNode(self):
        requires = Element("distroRequires")
        for child in self.child_nodes:
            requires.append(child.toXMLNode())
        return requires

class BeakerUnimplementedTag(BeakerBaseObject):
    """ When some tag is not implemented """

    def __init__(self):
        self.tag = "unknown"

    def toXMLNode(self):
        return Element(self.tag)

class BeakerRecipePartitions(BeakerUnimplementedTag):
    """ <repos> tag """
    def __init__(self):
        self.tag = "partitions"

class BeakerRecipeRepos(BeakerUnimplementedTag):
    """ <repos> tag """
    def __init__(self):
        self.tag = "repos"

class BeakerRecipeKsAppends(BeakerUnimplementedTag):
    """ <ks_appends> tag """
    def __init__(self):
        self.tag = "ks_appends"

class BeakerRecipePackages(BeakerUnimplementedTag):
    """ <repos> tag """
    def __init__(self):
        self.tag = "packages"

class BeakerRecipeWatchdog(BeakerBaseObject):
    """ <watchdog> tag """

    allowedPanic = ["None", "ignore"]
    def __init__(self, panic):
        if panic not in self.allowedPanic:
            raise UnknownPanicException
        self.panic = panic

    def toXMLNode(self):
        watchdog = Element("watchdog")
        watchdog.set("panic", self.panic)
        return watchdog

class BeakerRecipeAutopick(BeakerBaseObject):
    """ <autopick> tag """

    allowedPick = ["TRUE", "FALSE"]
    def __init__(self, random):
        if random.upper() not in self.allowedPick:
            raise UnknownPanicException
        self.random = random

    def toXMLNode(self):
        autopick = Element("autopick")
        autopick.set("random", self.random)
        return autopick

class BeakerRecipeKickstart(BeakerBaseObject):
    """ <kickstart> tag """

    def __init__(self, kickstart):
        self.kickstart = kickstart

    def toXMLNode(self):
        kickstart = Element("kickstart")
        kickstart.text = self.kickstart
        return kickstart

class BeakerRecipe(BeakerBaseObject):
    """ <recipe> tag """

    def __init__(self, kernel_options="", kernel_options_post="", ks_meta="method=nfs", role="None", whiteboard="", kickstart=None):
        self.kernel_options = kernel_options
        self.kernel_options_post = kernel_options_post
        self.ks_meta = ks_meta
        self.role = role
        self.whiteboard = whiteboard
        self.kickstart = kickstart
        self.autopick = BeakerRecipeAutopick(random="false")
        self.watchdog = BeakerRecipeWatchdog(panic="None")
        self.packages = BeakerRecipePackages()
        self.ks_appends = BeakerRecipeKsAppends()
        self.repos = BeakerRecipeRepos()
        self.distroreq = BeakerRecipeDistroRequires()
        self.hostreq = BeakerRecipeHostRequires()
        self.partitions = BeakerRecipePartitions()
        self.tasks = []

    def addTasks(self, task):
        if type(task) != list:
            self.tasks.append(task)
        else:
            self.tasks.extend(task)

    def setHostReqParam(self, req, value):
        to_parse = self.hostreq.child_nodes[:]
        success = False
        while to_parse != []:
            node = to_parse.pop()
            if type(node) == BeakerAnd or type(node) == BeakerOr:
                to_parse.extend(node.child_nodes)
            elif type(node) == BeakerRecipeHostRequirement:
                if node.req == req:
                    node.setReq(req, value)
                    success = True
            else:
                raise Exception("Faced unknown type in host_req -> %s" % str(type(node)))
        if not success:
            raise Exception("Host requirement %s was not found!" % req)

    def setDistroReqParam(self, req, value):
        to_parse = self.distroreq.child_nodes[:]
        success = False
        while to_parse != []:
            node = to_parse.pop()
            if type(node) == BeakerAnd or type(node) == BeakerOr:
                to_parse.extend(node.child_nodes)
            elif type(node) == BeakerRecipeDistroRequirement:
                if node.req == req:
                    node.setReq(req, value)
                    success = True
            else:
                raise Exception("Faced unknown type in distro_req -> %s" % str(type(node)))
        if not success:
            raise Exception("Distro requirement %s was not found!" % req)

    def toXMLNode(self):
        recipe = Element("recipe")
        recipe.set("kernel_options", self.kernel_options)
        recipe.set("kernel_options_post", self.kernel_options_post)
        recipe.set("ks_meta", self.ks_meta)
        recipe.set("role", self.role)
        recipe.set("whiteboard", self.whiteboard)
        if self.kickstart != None:
            recipe.append(self.kickstart.toXMLNode())
        recipe.append(self.autopick.toXMLNode())
        recipe.append(self.watchdog.toXMLNode())
        recipe.append(self.packages.toXMLNode())
        recipe.append(self.ks_appends.toXMLNode())
        recipe.append(self.repos.toXMLNode())
        recipe.append(self.distroreq.toXMLNode())
        recipe.append(self.hostreq.toXMLNode())
        recipe.append(self.partitions.toXMLNode())
        for task in self.tasks:
            recipe.append(task.toXMLNode())
        return recipe

class BeakerRecipeSet(BeakerBaseObject):
    """ <recipeSet> tag """

    allowedPriorities = ["High", "Low"]
    def __init__(self, priority="High", recipes=[]):
        if priority.title() not in self.allowedPriorities:
            raise UnknownPriorityException
        self.priority = priority.title()
        self.recipes = recipes
    
    def addRecipes(self, recipe):
        if type(recipe) != list:
            self.recipes.append(recipe)
        else:
            self.recipes.extend(recipe)

    def toXMLNode(self):
        recipeset = Element("recipeSet")
        recipeset.set("priority", self.priority)
        for recipe in self.recipes:
            recipeset.append(recipe.toXMLNode())
        return recipeset

class BeakerJob(BeakerBaseObject):
    """ <job> tag """

    def __init__(self, whiteboard="Default name", retention_tag="scratch", product=None, recipeset=BeakerRecipeSet()):
        self.retention_tag = retention_tag
        self.product = product
        self.whiteboard = whiteboard
        self.recipeset = recipeset

    def toXMLNode(self):
        job = Element("job")
        job.set("retention_tag", self.retention_tag)
        if self.product != None:
            job.set("product", self.product)
        whiteboard = Element("whiteboard")
        whiteboard.text = self.whiteboard
        job.append(whiteboard)
        job.append(self.recipeset.toXMLNode())
        return job

    def xmlRepresentation(self):
        io = StringIO()
        doc = ElementTree(self.toXMLNode())
        doc.write(io)
        return io.getvalue()

class BeakerJSONBuilder(object):
    """ Builds the tree from XML file or string """

    def __init__(self, data):
        f = open(data, "r")
        self.data = json.loads(f.read())
        f.close()
        self.buildStart()

    def callFunc(self, funcpostfix, data):
        return self.__getattribute__("buildRecipeset%s" % funcpostfix )(data)

    def getJob(self):
        return self.job

    def buildStart(self):
        self.job = BeakerJob()
        for key in self.data:
            if key == "whiteboard":
                self.job.setValue("whiteboard", self.data[key])
            elif key == "recipes":
                self.job.setValue("recipeset", self.buildRecipeset(self.data[key]))

    def buildRecipeset(self, data):
        recipeset = BeakerRecipeSet()
        if type(data) == dict:
            data = [data]
        for recipe in data:
            recipeObject = BeakerRecipe()
            for key in recipe:
                className = "BeakerRecipe%s" % key.title()
                if key == "tasks":
                    recipeObject.addTasks(self.buildRecipesetTasks(recipe[key]))
                elif key == "distro" or key == "host":
                    recipeObject.setValue("%sreq" % key, self.callFunc(key.title(), recipe[key]))
                else:
                    try:
                        recipeObject.setValue(key, globals()[className](recipe[key]))
                    except KeyError:
                        recipeObject.setValue(key, recipe[key])
            recipeset.addRecipes(recipeObject)

        return recipeset

    def buildRecipesetTasks(self, tasks):
        result_tasks = []
        for task in tasks:
            taskObject = BeakerRecipeTask(task["name"])
            if "params" in task:    
                for param in task["params"]:
                    taskObject.addParam(param, task["params"][param])
            result_tasks.append(taskObject)    
        return result_tasks
    
    def buildRecipesetDistro(self, data):
        distro_req = BeakerRecipeDistroRequires()
        if type(data) != list:
            data = [data]
        for item in data:
            if type(item) == dict:
                if len(item) != 1:
                    raise Exception("Unsupported! %s" % item)
                # And, Or nebo primo nejaka hodnota
                if item.keys()[0] in ["and", "or"]:
                    # Je to and nebo or
                    key = item.keys()[0]
                    if key == "and":
                        distro_req.addRequirement(self.buildRecipesetAnd(item[key], "Distro"))
                    else:
                        distro_req.addRequirement(self.buildRecipesetOr(item[key], "Distro"))
                else:
                    # Je to primo nejaka hodnota
                    distro_req.addRequirement(self.buildRecipesetDistroRequirement(item))
            else:
                raise Exception("Unknown JSON tag %s" % str(type(item)))
            
        return distro_req

    def buildRecipesetHost(self, data):
        host_req = BeakerRecipeHostRequires()
        if type(data) != list:
            data = [data]
        for item in data:
            if type(item) == dict:
                if len(item) != 1:
                    raise Exception("Unsupported! %s" % item)
                # And, Or nebo primo nejaka hodnota
                if item.keys()[0] in ["and", "or"]:
                    # Je to and nebo or
                    key = item.keys()[0]
                    if key == "and":
                        host_req.addRequirement(self.buildRecipesetAnd(item[key], "Host"))
                    else:
                        host_req.addRequirement(self.buildRecipesetOr(item[key], "Host"))
                else:
                    # Je to primo nejaka hodnota
                    host_req.addRequirement(self.buildRecipesetHostRequirement(item))
            else:
                raise Exception("Unknown JSON tag %s" % str(type(item)))
            
        return host_req

    def buildRecipesetAnd(self, data, kind):
        # And tag
        and_tag = BeakerAnd()
        if type(data) != list:
            raise Exception("AND can handle only LIST")
        for item in data:
            if len(item) != 1 or type(item) != dict:
                raise Exception("Items for requirements must have only one pair of key->value")
            and_tag.addRequirement(self.callFunc("%sRequirement" % kind, item))
        return and_tag

    def buildRecipesetOr(self, data, kind):
        # Or tag
        or_tag = BeakerOr()
        if type(data) != list:
            raise Exception("OR can handle only LIST")
        for item in data:
            if len(item) != 1 or type(item) != dict:
                raise Exception("Items for requirements must have only one pair of key->value")
            or_tag.addRequirement(self.callFunc("%sRequirement" % kind, item))
        return or_tag

    def buildRecipesetDistroRequirement(self, data):
        if len(data) != 1:
            raise Exception("Unsupported! %s" % data)
        req = data.keys()[0]
        value = data[req]
        requirement = BeakerRecipeDistroRequirement(req, value)
        return requirement

    def buildRecipesetHostRequirement(self, data):
        if len(data) != 1:
            raise Exception("Unsupported! %s" % data)
        req = data.keys()[0]
        value = data[req]
        requirement = BeakerRecipeHostRequirement(req, value)
        return requirement


def main(argv):
    argv.reverse()
    # Priklady:
    # ./bkr_job_gen.py load job.json task "/CloudForms/Installation/CloudEngine" param set "YUM_RELEASEVER" "6.2" param delete CF_CUSTOM_REPOS print
    job = None
    currentRecipe = 0
    currentTask = None
    username = None
    password = False
    closure = None
    while len(argv) > 0:
        command = argv.pop()
        if command == "load":
            # Load json file
            try:
                builder = BeakerJSONBuilder(argv.pop())
                job = builder.getJob()
            except IndexError:
                raise Exception("You must provide file name to import!")
            except IOError:
                raise Exception("Input file does not exist!")
        elif command == "user":
            # Set user name
            try:
                username = argv.pop()
            except IndexError:
                raise Exception("You must provide user name to set!")
        elif command == "pass":
            # Set user password
            try:
                password = argv.pop()
            except IndexError:
                raise Exception("You must provide user password to set!")
        elif command == "closure":
            # Set closure job
            try:
                closure = argv.pop()
            except IndexError:
                raise Exception("You must provide closure name where to stop!")
        elif command == "submit-watch":
            # Submit and watch job
            try:
                app = BeakerJobSubmitApplication(username, password, job, closure)
            except AttributeError:
                raise Exception("You must load JSON at first!")
        elif command == "print":
            try:
                print job.xmlRepresentation()
            except AttributeError:
                raise Exception("You must load the JSON file at first!")
        elif command == "kickstart":
            kickstart = None
            recipeset = None
            try:
                kickstart = argv.pop()
            except IndexError:
                raise Exception("You must specify the kickstart file")
            f = open(kickstart, "r")
            kickstart = f.read()
            f.close()
            # Find kickstart
            recipeset = job.recipeset
            try:
                for recipe in recipeset.recipes:
                    recipe.kickstart = BeakerRecipeKickstart(kickstart)
            except AttributeError:
                raise Exception("Bad error!")
        elif command == "recipe":
            recipeset = None
            try:
                recipeset = job.recipeset
            except AttributeError:
                raise Exception("You must load the JSON file at first!")
            try:
                currentRecipe = int(argv.pop())
            except IndexError:
                raise Exception("You must provide recipe number!")
            except ValueError:
                raise Exception("%s is not a recipe number!" % currentRecipe)
            try:
                recipeset.recipes[currentRecipe]
            except IndexError:
                raise Exception("There is no recipe with index %d" % currentRecipe)
        elif command == "task":
            # Find the task, put it into currentTask
            taskname = None
            recipe = None
            try:
                recipe = job.recipeset.recipes[currentRecipe]
            except AttributeError:
                raise Exception("You must load the JSON file at first!")
            try:
                taskname = argv.pop()
            except IndexError:
                raise Exception("You must provide task name!")
            tasks = recipe.tasks
            found = False
            for task in tasks:
                if task.name == taskname:
                    currentTask = task
                    found = True
                    break
            if not found:
                raise Exception("Task '%s' wasn't found!" % taskname)
        elif command == "param":
            subcommand = None
            try:
                subcommand = argv.pop()
            except IndexError:
                raise Exception("You must specify a subcommand for 'param'!")
            try:
                currentTask.params
            except AttributeError:
                raise Exception("You must specify task name at first!")
            paramname = None
            try:
                paramname = argv.pop()
            except IndexError:
                raise Exception("You must specify which parameter are you editing!")
            if subcommand == "set":
                # Najdeme parametr, ktery budeme upravovat, pripadne vytvorime novy
                param = None
                paramvalue = None
                try:
                    paramvalue = argv.pop()
                except IndexError:
                    raise Exception("You must specify new parameter value!")
                for p in currentTask.params:
                    if p.name == paramname:
                        param = p
                        break
                if param == None:
                    param = BeakerRecipeTaskParam(paramname, paramvalue)
                    currentTask.params.append(param)
                else:
                    param.value = paramvalue
            elif subcommand == "delete":
                success = False
                for p in currentTask.params:
                    if p.name == paramname:
                        del currentTask.params[currentTask.params.index(p)]
                        success = True
                        break
                if not success:
                    raise Exception("Parameter '%s' wasn't found for deletion!" % paramname)
            else:
                raise Exception("Unknown command for 'param' -> %s" % subcommand)
        elif command == "requires":
            subcommand = None
            try:
                subcommand = argv.pop()
            except IndexError:
                raise Exception("You must specify a subcommand for 'param'!")
            try:
                job.recipeset
            except AttributeError:
                raise Exception("You must load the JSON at first!")
            if subcommand == "host":
                name = None
                try:
                    name = argv.pop()
                except IndexError:
                    raise Exception("You must specify a name for requires host operation!")
                operation = None
                try:
                    operation = argv.pop()
                except IndexError:
                    raise Exception("You must specify an operation for requires host operation!")
                if operation == "set":
                    value = None
                    try:
                        value = argv.pop()
                    except IndexError:
                        raise Exception("You must specify a value for requires host set operation!")
                    recipe = job.recipeset.recipes[currentRecipe]
                    recipe.setHostReqParam(name, value)

                else:
                    raise Exception("Unknown operation %s for required host!" % operation)
            elif subcommand == "distro":
                name = None
                try:
                    name = argv.pop()
                except IndexError:
                    raise Exception("You must specify a name for requires distro operation!")
                operation = None
                try:
                    operation = argv.pop()
                except IndexError:
                    raise Exception("You must specify an operation for requires distro operation!")
                if operation == "set":
                    value = None
                    try:
                        value = argv.pop()
                    except IndexError:
                        raise Exception("You must specify a value for requires distro set operation!")
                    recipe = job.recipeset.recipes[currentRecipe]
                    recipe.setDistroReqParam(name, value)

                else:
                    raise Exception("Unknown operation %s for required host!" % operation)
            else:
                raise Exception("Unknown subcommand %s for %s" % (subcommand, command))
        else:
            raise Exception("Unknown command %s" % command)
    return job

if __name__ == "__main__":
    main(sys.argv[1:])
