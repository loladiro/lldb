# a wrapper for the Objective-C runtime for use by LLDB
import lldb
import cache

class Utilities:
	@staticmethod
	def read_ascii(process, pointer,max_len=128):
		error = lldb.SBError()
		content = None
		try:
			content = process.ReadCStringFromMemory(pointer,max_len,error)
		except:
			pass
		if content == None or len(content) == 0 or error.fail == True:
			return None
		return content

	@staticmethod
	def is_valid_pointer(pointer, pointer_size, allow_tagged=False, allow_NULL=False):
		if pointer == None:
			return False
		if pointer == 0:
			return allow_NULL
		if allow_tagged and (pointer % 2) == 1:
			return True
		return ((pointer % pointer_size) == 0)

	# Objective-C runtime has a rule that pointers in a class_t will only have bits 0 thru 46 set
	# so if any pointer has bits 47 thru 63 high we know that this is not a valid isa
	@staticmethod
	def is_allowed_pointer(pointer):
		if pointer == None:
			return False
		return ((pointer & 0xFFFF800000000000) == 0)

	@staticmethod
	def read_child_of(valobj,offset,type):
		child = valobj.CreateChildAtOffset("childUNK",offset,type)
		if child == None or child.IsValid() == False:
			return None;
		return child.GetValueAsUnsigned()

	@staticmethod
	def is_valid_identifier(name):
		if name is None:
			return None
		if len(name) == 0:
			return None
		# technically, the ObjC runtime does not enforce any rules about what name a class can have
		# in practice, the commonly used byte values for a class name are the letters, digits and some
		# symbols: $, %, -, _, .
		# WARNING: this means that you cannot use this runtime implementation if you need to deal
		# with class names that use anything but what is allowed here
		ok_values = dict.fromkeys("$%_.-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz1234567890")
		return all(c in ok_values for c in name)

	@staticmethod
	def check_is_osx_lion(target):
		# assume the only thing that has a Foundation.framework is a Mac
		# assume anything < Lion does not even exist
		mod = target.module['Foundation']
		if mod == None or mod.IsValid() == False:
			return None
		ver = mod.GetVersion()
		if ver == None or ver == []:
			return None
		return (ver[0] < 900)

class RoT_Data:
	def __init__(self,rot_pointer,params):
		if (Utilities.is_valid_pointer(rot_pointer.GetValueAsUnsigned(),params.pointer_size, allow_tagged=False)):
			self.sys_params = params
			self.valobj = rot_pointer
			#self.flags = Utilities.read_child_of(self.valobj,0,self.sys_params.uint32_t)
			self.instanceStart = Utilities.read_child_of(self.valobj,4,self.sys_params.uint32_t)
			self.instanceSize = Utilities.read_child_of(self.valobj,8,self.sys_params.uint32_t)
			offset = 24 if self.sys_params.is_64_bit else 16
			#self.ivarLayoutPtr = Utilities.read_child_of(self.valobj,offset,self.sys_params.addr_ptr_type)
			self.namePointer = Utilities.read_child_of(self.valobj,offset,self.sys_params.addr_ptr_type)
			self.check_valid()
		else:
			self.valid = False
		if self.valid:
			self.name = Utilities.read_ascii(self.valobj.GetTarget().GetProcess(),self.namePointer)
			if not(Utilities.is_valid_identifier(self.name)):
				self.valid = False

	# perform sanity checks on the contents of this class_rw_t
	def check_valid(self):
		self.valid = True
		# misaligned pointers seem to be possible for this field
		#if not(Utilities.is_valid_pointer(self.namePointer,self.sys_params.pointer_size,allow_tagged=False)):
		#	self.valid = False
		#	pass

	def __str__(self):
		return \
		 "instanceStart = " + hex(self.instanceStart) + "\n" + \
		 "instanceSize = " + hex(self.instanceSize) + "\n" + \
		 "namePointer = " + hex(self.namePointer) + " --> " + self.name

	def is_valid(self):
		return self.valid


class RwT_Data:
	def __init__(self,rwt_pointer,params):
		if (Utilities.is_valid_pointer(rwt_pointer.GetValueAsUnsigned(),params.pointer_size, allow_tagged=False)):
			self.sys_params = params
			self.valobj = rwt_pointer
			#self.flags = Utilities.read_child_of(self.valobj,0,self.sys_params.uint32_t)
			#self.version = Utilities.read_child_of(self.valobj,4,self.sys_params.uint32_t)
			self.roPointer = Utilities.read_child_of(self.valobj,8,self.sys_params.addr_ptr_type)
			self.check_valid()
		else:
			self.valid = False
		if self.valid:
			self.rot = self.valobj.CreateValueFromAddress("rot",self.roPointer,self.sys_params.addr_ptr_type).AddressOf()
			self.data = RoT_Data(self.rot,self.sys_params)

	# perform sanity checks on the contents of this class_rw_t
	def check_valid(self):
		self.valid = True
		if not(Utilities.is_valid_pointer(self.roPointer,self.sys_params.pointer_size,allow_tagged=False)):
			self.valid = False

	def __str__(self):
		return \
		 "roPointer = " + hex(self.roPointer)

	def is_valid(self):
		if self.valid:
			return self.data.is_valid()
		return False

class Class_Data_V2:
	def __init__(self,isa_pointer,params):
		if (isa_pointer != None) and (Utilities.is_valid_pointer(isa_pointer.GetValueAsUnsigned(),params.pointer_size, allow_tagged=False)):
			self.sys_params = params
			self.valobj = isa_pointer
			self.isaPointer = Utilities.read_child_of(self.valobj,0,self.sys_params.addr_ptr_type)
			self.superclassIsaPointer = Utilities.read_child_of(self.valobj,1*self.sys_params.pointer_size,self.sys_params.addr_ptr_type)
			self.cachePointer = Utilities.read_child_of(self.valobj,2*self.sys_params.pointer_size,self.sys_params.addr_ptr_type)
			self.vtablePointer = Utilities.read_child_of(self.valobj,3*self.sys_params.pointer_size,self.sys_params.addr_ptr_type)
			self.dataPointer = Utilities.read_child_of(self.valobj,4*self.sys_params.pointer_size,self.sys_params.addr_ptr_type)
			self.check_valid()
		else:
			self.valid = False
		if self.valid:
			self.rwt = self.valobj.CreateValueFromAddress("rwt",self.dataPointer,self.sys_params.addr_ptr_type).AddressOf()
			self.data = RwT_Data(self.rwt,self.sys_params)

	# perform sanity checks on the contents of this class_t
	def check_valid(self):
		self.valid = True
		if not(Utilities.is_valid_pointer(self.isaPointer,self.sys_params.pointer_size,allow_tagged=False)):
			self.valid = False
			return
		if not(Utilities.is_valid_pointer(self.superclassIsaPointer,self.sys_params.pointer_size,allow_tagged=False)):
			# NULL is a valid value for superclass (it means we have reached NSObject)
			if self.superclassIsaPointer != 0:
				self.valid = False
				return
		if not(Utilities.is_valid_pointer(self.cachePointer,self.sys_params.pointer_size,allow_tagged=False)):
			self.valid = False
			return
		if not(Utilities.is_valid_pointer(self.vtablePointer,self.sys_params.pointer_size,allow_tagged=False)):
			self.valid = False
			return
		if not(Utilities.is_valid_pointer(self.dataPointer,self.sys_params.pointer_size,allow_tagged=False)):
			self.valid = False
			return
		if not(Utilities.is_allowed_pointer(self.isaPointer)):
			self.valid = False
			return
		if not(Utilities.is_allowed_pointer(self.superclassIsaPointer)):
			# NULL is a valid value for superclass (it means we have reached NSObject)
			if self.superclassIsaPointer != 0:
				self.valid = False
				return
		if not(Utilities.is_allowed_pointer(self.cachePointer)):
			self.valid = False
			return
		if not(Utilities.is_allowed_pointer(self.vtablePointer)):
			self.valid = False
			return
		if not(Utilities.is_allowed_pointer(self.dataPointer)):
			self.valid = False
			return

	# in general, KVO is implemented by transparently subclassing
	# however, there could be exceptions where a class does something else
	# internally to implement the feature - this method will have no clue that a class
	# has been KVO'ed unless the standard implementation technique is used
	def is_kvo(self):
		if self.is_valid():
			if self.class_name().startswith("NSKVONotifying_"):
				return True
		return False

	def get_superclass(self):
		if self.is_valid():
			parent_isa_pointer = self.valobj.CreateChildAtOffset("parent_isa",
				self.sys_params.pointer_size,
				self.sys_params.addr_ptr_type)
			return Class_Data_V2(parent_isa_pointer,self.sys_params)
		else:
			return None

	def class_name(self):
		if self.is_valid():
			return self.data.data.name
		else:
			return None

	def is_valid(self):
		if self.valid:
			return self.data.is_valid()
		return False

	def __str__(self):
		return 'isaPointer = ' + hex(self.isaPointer) + "\n" + \
		 "superclassIsaPointer = " + hex(self.superclassIsaPointer) + "\n" + \
		 "cachePointer = " + hex(self.cachePointer) + "\n" + \
		 "vtablePointer = " + hex(self.vtablePointer) + "\n" + \
		 "data = " + hex(self.dataPointer)

	def is_tagged(self):
		return False

	def instance_size(self,align=False):
		if self.is_valid() == False:
			return None
		if align:
			unalign = self.instance_size(False)
			if self.sys_params.is_64_bit:
				return ((unalign + 7) & ~7) % 0x100000000
			else:
				return ((unalign + 3) & ~3) % 0x100000000
		else:
			return self.rwt.rot.instanceSize

# runtime v1 is much less intricate than v2 and stores relevant information directly in the class_t object
class Class_Data_V1:
	def __init__(self,isa_pointer,params):
		if (isa_pointer != None) and (Utilities.is_valid_pointer(isa_pointer.GetValueAsUnsigned(),params.pointer_size, allow_tagged=False)):
			self.valid = True
			self.sys_params = params
			self.valobj = isa_pointer
			self.isaPointer = Utilities.read_child_of(self.valobj,0,self.sys_params.addr_ptr_type)
			self.superclassIsaPointer = Utilities.read_child_of(self.valobj,1*self.sys_params.pointer_size,self.sys_params.addr_ptr_type)
			self.namePointer = Utilities.read_child_of(self.valobj,2*self.sys_params.pointer_size,self.sys_params.addr_ptr_type)
			self.version = Utilities.read_child_of(self.valobj,3*self.sys_params.pointer_size,self.sys_params.addr_ptr_type)
			self.info = Utilities.read_child_of(self.valobj,4*self.sys_params.pointer_size,self.sys_params.addr_ptr_type)
			self.instanceSize = Utilities.read_child_of(self.valobj,5*self.sys_params.pointer_size,self.sys_params.addr_ptr_type)
		else:
			self.valid = False
		if self.valid:
			self.name = Utilities.read_ascii(self.valobj.GetTarget().GetProcess(),self.namePointer)
			if not(Utilities.is_valid_identifier(self.name)):
				self.valid = False

	# perform sanity checks on the contents of this class_t
	def check_valid(self):
		self.valid = True
		if not(Utilities.is_valid_pointer(self.isaPointer,self.sys_params.pointer_size,allow_tagged=False)):
			self.valid = False
			return
		if not(Utilities.is_valid_pointer(self.superclassIsaPointer,self.sys_params.pointer_size,allow_tagged=False)):
			# NULL is a valid value for superclass (it means we have reached NSObject)
			if self.superclassIsaPointer != 0:
				self.valid = False
				return
		if not(Utilities.is_valid_pointer(self.namePointer,self.sys_params.pointer_size,allow_tagged=False,allow_NULL=True)):
			self.valid = False
			return

	# in general, KVO is implemented by transparently subclassing
	# however, there could be exceptions where a class does something else
	# internally to implement the feature - this method will have no clue that a class
	# has been KVO'ed unless the standard implementation technique is used
	def is_kvo(self):
		if self.is_valid():
			if self.class_name().startswith("NSKVONotifying_"):
				return True
		return False

	def get_superclass(self):
		if self.is_valid():
			parent_isa_pointer = self.valobj.CreateChildAtOffset("parent_isa",
				self.sys_params.pointer_size,
				self.sys_params.addr_ptr_type)
			return Class_Data_V1(parent_isa_pointer,self.sys_params)
		else:
			return None

	def class_name(self):
		if self.is_valid():
			return self.name
		else:
			return None

	def is_valid(self):
		return self.valid

	def __str__(self):
		return 'isaPointer = ' + hex(self.isaPointer) + "\n" + \
		 "superclassIsaPointer = " + hex(self.superclassIsaPointer) + "\n" + \
		 "namePointer = " + hex(self.namePointer) + " --> " + self.name + \
		 "version = " + hex(self.version) + "\n" + \
		 "info = " + hex(self.info) + "\n" + \
		 "instanceSize = " + hex(self.instanceSize) + "\n"

	def is_tagged(self):
		return False

	def instance_size(self,align=False):
		if self.is_valid() == False:
			return None
		if align:
			unalign = self.instance_size(False)
			if self.sys_params.is_64_bit:
				return ((unalign + 7) & ~7) % 0x100000000
			else:
				return ((unalign + 3) & ~3) % 0x100000000
		else:
			return self.instanceSize

# these are the only tagged pointers values for current versions
# of OSX - they might change in future OS releases, and no-one is
# advised to rely on these values, or any of the bitmasking formulas
# in TaggedClass_Data. doing otherwise is at your own risk
TaggedClass_Values_Lion = {1 : 'NSNumber', \
                           5: 'NSManagedObject', \
                           6: 'NSDate', \
                           7: 'NSDateTS' };
TaggedClass_Values_NMOS = {0: 'NSAtom', \
                           3 : 'NSNumber', \
                           4: 'NSDateTS', \
                           5: 'NSManagedObject', \
                           6: 'NSDate' };

class TaggedClass_Data:
	def __init__(self,pointer,params):
		global TaggedClass_Values_Lion,TaggedClass_Values_NMOS
		self.valid = True
		self.name = None
		self.sys_params = params
		self.valobj = pointer
		self.val = (pointer & ~0x0000000000000000FF) >> 8
		self.class_bits = (pointer & 0xE) >> 1
		self.i_bits = (pointer & 0xF0) >> 4
		
		if self.sys_params.is_lion:
			if self.class_bits in TaggedClass_Values_Lion:
				self.name = TaggedClass_Values_Lion[self.class_bits]
			else:
				self.valid = False
		else:
			if self.class_bits in TaggedClass_Values_NMOS:
				self.name = TaggedClass_Values_NMOS[self.class_bits]
			else:
				self.valid = False


	def is_valid(self):
		return self.valid

	def class_name(self):
		if self.is_valid():
			return self.name
		else:
			return False

	def value(self):
		return self.val if self.is_valid() else None

	def info_bits(self):
		return self.i_bits if self.is_valid() else None

	def is_kvo(self):
		return False

	# we would need to go around looking for the superclass or ask the runtime
	# for now, we seem not to require support for this operation so we will merrily
	# pretend to be at a root point in the hierarchy
	def get_superclass(self):
		return None

	# anything that is handled here is tagged
	def is_tagged(self):
		return True

	# it seems reasonable to say that a tagged pointer is the size of a pointer
	def instance_size(self,align=False):
		if self.is_valid() == False:
			return None
		return 8 if self.sys_params.is_64_bit else 4


class InvalidClass_Data:
	def __init__(self):
		pass
	def is_valid(self):
		return False

runtime_version = cache.Cache()
os_version = cache.Cache()

class SystemParameters:
	def __init__(self,valobj):
		self.adjust_for_architecture(valobj)

	def adjust_for_architecture(self,valobj):
		self.process = valobj.GetTarget().GetProcess()
		self.is_64_bit = (self.process.GetAddressByteSize() == 8)
		self.is_little = (self.process.GetByteOrder() == lldb.eByteOrderLittle)
		self.pointer_size = self.process.GetAddressByteSize()
		self.addr_type = valobj.GetType().GetBasicType(lldb.eBasicTypeUnsignedLong)
		self.addr_ptr_type = self.addr_type.GetPointerType()
		self.uint32_t = valobj.GetType().GetBasicType(lldb.eBasicTypeUnsignedInt)
		global runtime_version
		global os_version
		pid = self.process.GetProcessID()
		if runtime_version.look_for_key(pid):
			self.runtime_version = runtime_version.get_value(pid)
		else:
			self.runtime_version = ObjCRuntime.runtime_version(self.process)
			runtime_version.add_item(pid,self.runtime_version)
		if os_version.look_for_key(pid):
			self.is_lion = os_version.get_value(pid)
		else:
			self.is_lion = Utilities.check_is_osx_lion(valobj.GetTarget())
			os_version.add_item(pid,self.is_lion)

isa_cache = cache.Cache()

class ObjCRuntime:

	# the ObjC runtime has no explicit "version" field that we can use
	# instead, we discriminate v1 from v2 by looking for the presence
	# of a well-known section only present in v1
	@staticmethod
	def runtime_version(process):
		if process.IsValid() == False:
			return None
		target = process.GetTarget()
		num_modules = target.GetNumModules()
		module_objc = None
		for idx in range(num_modules):
			module = target.GetModuleAtIndex(idx)
			if module.GetFileSpec().GetFilename() == 'libobjc.A.dylib':
				module_objc = module
				break
		if module_objc == None or module_objc.IsValid() == False:
			return None
		num_sections = module.GetNumSections()
		section_objc = None
		for idx in range(num_sections):
			section = module.GetSectionAtIndex(idx)
			if section.GetName() == '__OBJC':
				section_objc = section
				break
		if section_objc != None and section_objc.IsValid():
			return 1
		return 2

	def __init__(self,valobj):
		self.valobj = valobj
		self.adjust_for_architecture()
		self.sys_params = SystemParameters(self.valobj)
		self.unsigned_value = self.valobj.GetValueAsUnsigned()
		self.isa_value = None

	def adjust_for_architecture(self):
		self.is_64_bit = (self.valobj.GetTarget().GetProcess().GetAddressByteSize() == 8)
		self.is_little = (self.valobj.GetTarget().GetProcess().GetByteOrder() == lldb.eByteOrderLittle)
		self.pointer_size = self.valobj.GetTarget().GetProcess().GetAddressByteSize()
		self.addr_type = self.valobj.GetType().GetBasicType(lldb.eBasicTypeUnsignedLong)
		self.addr_ptr_type = self.addr_type.GetPointerType()

# an ObjC pointer can either be tagged or must be aligned
	def is_tagged(self):
		if self.valobj is None:
			return False
		return (Utilities.is_valid_pointer(self.unsigned_value,self.pointer_size, allow_tagged=True) and \
		not(Utilities.is_valid_pointer(self.unsigned_value,self.pointer_size, allow_tagged=False)))

	def is_valid(self):
		if self.valobj is None:
			return False
		if self.valobj.IsInScope() == False:
			return False
		return Utilities.is_valid_pointer(self.unsigned_value,self.pointer_size, allow_tagged=True)

	def read_isa(self):
		if self.isa_value != None:
			return self.isa_value
		isa_pointer = self.valobj.CreateChildAtOffset("cfisa",
			0,
			self.addr_ptr_type)
		if isa_pointer == None or isa_pointer.IsValid() == False:
			return None;
		if isa_pointer.GetValueAsUnsigned(1) == 1:
			return None;
		self.isa_value = isa_pointer
		return isa_pointer

	def read_class_data(self):
		global isa_cache
		if self.is_tagged():
			# tagged pointers only exist in ObjC v2
			if self.sys_params.runtime_version == 2:
				# not every odd-valued pointer is actually tagged. most are just plain wrong
				# we could try and predetect this before even creating a TaggedClass_Data object
				# but unless performance requires it, this seems a cleaner way to tackle the task
				tentative_tagged = TaggedClass_Data(self.unsigned_value,self.sys_params)
				return tentative_tagged if tentative_tagged.is_valid() else InvalidClass_Data()
			else:
				return InvalidClass_Data()
		if self.is_valid() == False:
			return InvalidClass_Data()
		isa = self.read_isa()
		if isa == None:
			return InvalidClass_Data()
		isa_value = isa.GetValueAsUnsigned(1)
		if isa_value == 1:
			return InvalidClass_Data()
		data = isa_cache.get_value(isa_value,default=None)
		if data != None:
			return data
		if self.sys_params.runtime_version == 2:
			data = Class_Data_V2(isa,self.sys_params)
		else:
			data = Class_Data_V1(isa,self.sys_params)
		if data == None:
			return InvalidClass_Data()
		if data.is_valid():
			isa_cache.add_item(isa_value,data,ok_to_replace=True)
		return data
