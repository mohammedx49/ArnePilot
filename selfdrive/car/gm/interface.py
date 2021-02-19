#!/usr/bin/env python3
from cereal import car, arne182
from common.numpy_fast import interp
from selfdrive.config import Conversions as CV
from selfdrive.car.gm.values import CAR, Ecu, ECU_FINGERPRINT, CruiseButtons, \
                                    AccState, FINGERPRINTS
from selfdrive.car import STD_CARGO_KG, scale_rot_inertia, scale_tire_stiffness, is_ecu_disconnected, gen_empty_fingerprint
from selfdrive.car.interfaces import CarInterfaceBase
from common.op_params import opParams

ButtonType = car.CarState.ButtonEvent.Type
EventName = car.CarEvent.EventName

op_params = opParams()
#STEER_RATIO = op_params.get('steer_ratio', default = 13.2)
TIRE_STIFFNESS = op_params.get('tire_stiffness', default = 0.5)
STEER_RATE = op_params.get('steer_rate', default = 1.0)
STEER_DELAY = op_params.get('steer_delay', default = 0.3)

#LQR_SCALE = op_params.get('lqr_scale', default = 1500.0)
#LQR_KI = op_params.get('lqr_ki', default = 0.06)

INDI_OLG = op_params.get('indi_olg', default = 15.0)
INDI_ILG = op_params.get('indi_ilg', default = 6.0)
INDI_TIME = op_params.get('indi_time', default = 5.5)
INDI_ACTUATOR = op_params.get('lqr_act', default = 6.0)

PID_KP1 = op_params.get('kp1', default = 0.1)
PID_KP2 = op_params.get('kp2', default = 0.24)
PID_KI1 = op_params.get('ki1', default = 0.01)
PID_KI2 = op_params.get('ki2', default = 0.019)
PID_KF = op_params.get('kf', default = 0.00004)

class CarInterface(CarInterfaceBase):

  @staticmethod
  def compute_gb(accel, speed):
    return float(accel) / 4.0

  @staticmethod
  def get_params(candidate, fingerprint=gen_empty_fingerprint(), has_relay=False, car_fw=[]):  # pylint: disable=dangerous-default-value
    ret = CarInterfaceBase.get_std_params(candidate, fingerprint, has_relay)
    ret.carName = "gm"
    ret.safetyModel = car.CarParams.SafetyModel.gm  # default to gm
    ret.enableCruise = False  # stock cruise control is kept off

    # GM port is considered a community feature, since it disables AEB;
    # TODO: make a port that uses a car harness and it only intercepts the camera
    ret.communityFeature = True

    # Presence of a camera on the object bus is ok.
    # Have to go to read_only if ASCM is online (ACC-enabled cars),
    # or camera is on powertrain bus (LKA cars without ACC).
    ret.enableCamera = is_ecu_disconnected(fingerprint[0], FINGERPRINTS, ECU_FINGERPRINT, candidate, Ecu.fwdCamera) or has_relay
    ret.openpilotLongitudinalControl = ret.enableCamera
    tire_stiffness_factor = 0.444  # not optimized yet

    # Start with a baseline lateral tuning for all GM vehicles. Override tuning as needed in each model section below.
    #ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP, ret.lateralTuning.pid.kfBP = [[0.], [0.], [0.]]
    #ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV, ret.lateralTuning.pid.kfV = [[0.2], [0.00], [0.00004]]   # full torque for 20 deg at 80mph means 0.00007818594
    #ret.steerRateCost = 1.0
    #ret.steerActuatorDelay = 0.3  # Default delay, not measured yet
    ret.steerActuatorDelay = STEER_DELAY
    ret.steerRateCost = STEER_RATE
    ret.enableGasInterceptor = 0x201 in fingerprint[0]

    if candidate == CAR.VOLT:
      # supports stop and go, but initial engage must be above 18mph (which include conservatism)
      ret.minEnableSpeed = 18 * CV.MPH_TO_MS
      ret.mass = 1607. + STD_CARGO_KG
      ret.wheelbase = 2.69
      ret.steerRatio = 15.7
      ret.steerRatioRear = 0.
      ret.centerToFront = ret.wheelbase * 0.4  # wild guess

    elif candidate == CAR.BOLT:
      # initial engage unkown - copied from Volt. Stop and go unknown.
      ret.minEnableSpeed = -1.
      ret.mass = 1616. + STD_CARGO_KG
      ret.wheelbase = 2.60096
      ret.steerRatio = 13.2
      #ret.steerRatio = STEER_RATIO
      ret.steerRatioRear = 0.
      ret.centerToFront = ret.wheelbase * 0.4 # wild guess

      #ret.lateralTuning.init('indi')
      #ret.lateralTuning.indi.innerLoopGain = INDI_OLG
      #ret.lateralTuning.indi.outerLoopGain = INDI_ILG
      #ret.lateralTuning.indi.timeConstant = INDI_TIME
      #ret.lateralTuning.indi.actuatorEffectiveness = INDI_ACTUATOR

      #ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0., 41.0], [0., 41.0]]
      #ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[PID_KP1, PID_KP2], [PID_KI1, PID_KI2]]
      #ret.lateralTuning.pid.kf = PID_KF

      ret.lateralTuning.init('lqr') #Rav4 from Arnepilot
      ret.lateralTuning.lqr.scale = 1500.0
      ret.lateralTuning.lqr.ki = 0.05
      ret.lateralTuning.lqr.a = [0., 1., -0.22619643, 1.21822268]
      ret.lateralTuning.lqr.b = [-1.92006585e-04, 3.95603032e-05]
      ret.lateralTuning.lqr.c = [1., 0.]
      ret.lateralTuning.lqr.k = [-110.73572306, 451.22718255]
      ret.lateralTuning.lqr.l = [0.3233671, 0.3185757]
      ret.lateralTuning.lqr.dcGain = 0.002237852961363602

      #tire_stiffness_factor = 0.5
      tire_stiffness_factor = TIRE_STIFFNESS

    elif candidate == CAR.MALIBU:
      # supports stop and go, but initial engage must be above 18mph (which include conservatism)
      ret.minEnableSpeed = 18 * CV.MPH_TO_MS
      ret.mass = 1496. + STD_CARGO_KG
      ret.wheelbase = 2.83
      ret.steerRatio = 15.8
      ret.steerRatioRear = 0.
      ret.centerToFront = ret.wheelbase * 0.4  # wild guess

    elif candidate == CAR.HOLDEN_ASTRA:
      ret.mass = 1363. + STD_CARGO_KG
      ret.wheelbase = 2.662
      # Remaining parameters copied from Volt for now
      ret.centerToFront = ret.wheelbase * 0.4
      ret.minEnableSpeed = 18 * CV.MPH_TO_MS
      ret.steerRatio = 15.7
      ret.steerRatioRear = 0.

    elif candidate == CAR.ACADIA:
      ret.minEnableSpeed = -1.  # engage speed is decided by pcm
      ret.mass = 4353. * CV.LB_TO_KG + STD_CARGO_KG
      ret.wheelbase = 2.86
      ret.steerRatio = 14.4  # end to end is 13.46
      ret.steerRatioRear = 0.
      ret.centerToFront = ret.wheelbase * 0.4

    elif candidate == CAR.BUICK_REGAL:
      ret.minEnableSpeed = 18 * CV.MPH_TO_MS
      ret.mass = 3779. * CV.LB_TO_KG + STD_CARGO_KG  # (3849+3708)/2
      ret.wheelbase = 2.83  # 111.4 inches in meters
      ret.steerRatio = 14.4  # guess for tourx
      ret.steerRatioRear = 0.
      ret.centerToFront = ret.wheelbase * 0.4  # guess for tourx

    elif candidate == CAR.CADILLAC_ATS:
      ret.minEnableSpeed = 18 * CV.MPH_TO_MS
      ret.mass = 1601. + STD_CARGO_KG
      ret.wheelbase = 2.78
      ret.steerRatio = 15.3
      ret.steerRatioRear = 0.
      ret.centerToFront = ret.wheelbase * 0.49
      
    elif candidate == CAR.ESCALADE:
      ret.minEnableSpeed = 18 * CV.MPH_TO_MS
      ret.mass = 2645. + STD_CARGO_KG
      ret.safetyModel = car.CarParams.SafetyModel.gm
      ret.wheelbase = 3.30
      ret.steerRatio = 15.4
      ret.steerRatioRear = 0.
      ret.centerToFront = ret.wheelbase * 0.4  # wild guess

      ret.lateralTuning.init('lqr') #Rav4 from Arnepilot
      ret.lateralTuning.lqr.scale = 1500.0
      ret.lateralTuning.lqr.ki = 0.05
      ret.lateralTuning.lqr.a = [0., 1., -0.22619643, 1.21822268]
      ret.lateralTuning.lqr.b = [-1.92006585e-04, 3.95603032e-05]
      ret.lateralTuning.lqr.c = [1., 0.]
      ret.lateralTuning.lqr.k = [-110.73572306, 451.22718255]
      ret.lateralTuning.lqr.l = [0.3233671, 0.3185757]
      ret.lateralTuning.lqr.dcGain = 0.002237852961363602

      #tire_stiffness_factor = 0.5
      tire_stiffness_factor = TIRE_STIFFNESS

    # TODO: get actual value, for now starting with reasonable value for
    # civic and scaling by mass and wheelbase
    ret.rotationalInertia = scale_rot_inertia(ret.mass, ret.wheelbase)

    # TODO: start from empirically derived lateral slip stiffness for the civic and scale by
    # mass and CG position, so all cars will have approximately similar dyn behaviors
    ret.tireStiffnessFront, ret.tireStiffnessRear = scale_tire_stiffness(ret.mass, ret.wheelbase, ret.centerToFront,
                                                                         tire_stiffness_factor=tire_stiffness_factor)

    ret.longitudinalTuning.kpBP = [0., 35.]
    ret.longitudinalTuning.kpV = [0.6, 0.7]
    ret.longitudinalTuning.kiBP = [0., 35.]
    ret.longitudinalTuning.kiV = [0.12, 0.2]

    if ret.enableGasInterceptor:
      ret.gasMaxBP = [0., 9., 35]
      ret.gasMaxV = [0.25, 0.5, 0.7]

    ret.stoppingControl = False
    ret.startAccel = 1.0

    ret.steerLimitTimer = 0.4
    ret.radarTimeStep = 0.0667  # GM radar runs at 15Hz instead of standard 20Hz

    return ret

  # returns a car.CarState
  def update(self, c, can_strings):
    ret_arne182 = arne182.CarStateArne182.new_message()
    self.cp.update_strings(can_strings)

    ret = self.CS.update(self.cp)

    ret.canValid = self.cp.can_valid
    ret.steeringRateLimited = self.CC.steer_rate_limited if self.CC is not None else False

    ret.cruiseState.available = self.CS.main_on
    ret.cruiseState.enabled = self.CS.main_on

    buttonEvents = []

    if self.CS.cruise_buttons != self.CS.prev_cruise_buttons and self.CS.prev_cruise_buttons != CruiseButtons.INIT:
      be = car.CarState.ButtonEvent.new_message()
      be.type = ButtonType.unknown
      if self.CS.cruise_buttons != CruiseButtons.UNPRESS:
        be.pressed = True
        but = self.CS.cruise_buttons
      else:
        be.pressed = False
        but = self.CS.prev_cruise_buttons
      if but == CruiseButtons.RES_ACCEL:
        #if not (ret.cruiseState.enabled and ret.standstill):
        be.type = ButtonType.accelCruise  # Suppress resume button if we're resuming from stop so we don't adjust speed.
      elif but == CruiseButtons.DECEL_SET:
        be.type = ButtonType.decelCruise
      elif but == CruiseButtons.CANCEL:
        be.type = ButtonType.cancel
      elif but == CruiseButtons.MAIN:
        be.type = ButtonType.altButton3
      buttonEvents.append(be)

    ret.buttonEvents = buttonEvents

    events, events_arne182 = self.create_common_events(ret)

    if ret.brakePressed:
      events.add(EventName.pedalPressed)
    if ret.vEgo < self.CP.minEnableSpeed:
      events.add(EventName.belowEngageSpeed)
    if self.CS.park_brake:
      events.add(EventName.parkBrake)

    # handle button presses
    #for b in ret.buttonEvents:
      # do enable on both accel and decel buttons
      #if b.type in [ButtonType.accelCruise, ButtonType.decelCruise] and not b.pressed:
        #events.add(EventName.buttonEnable)

    ret.events = events.to_msg()
    ret_arne182.events = events_arne182.to_msg()

    # copy back carState packet to CS
    self.CS.out = ret.as_reader()

    return self.CS.out, ret_arne182.as_reader()

  def apply(self, c):
    hud_v_cruise = c.hudControl.setSpeed
    if hud_v_cruise > 70:
      hud_v_cruise = 0

    # For Openpilot, "enabled" includes pre-enable.
    # In GM, PCM faults out if ACC command overlaps user gas.
    #enabled = c.enabled and not self.CS.out.gasPressed

    can_sends = self.CC.update(c.enabled, self.CS, self.frame, \
                               c.actuators,
                               hud_v_cruise, c.hudControl.lanesVisible,
                               c.hudControl.leadVisible, c.hudControl.visualAlert)

    self.frame += 1
    return can_sends
