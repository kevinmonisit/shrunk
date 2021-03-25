/**
 * Implements the [[ShareLinkModal]] component
 * @packageDocumentation
 */

import React from 'react';
import {
  Col,
  Modal,
  Form,
  Input,
  Button,
  Radio,
  Row,
  Select,
  Space,
  Table,
  Tag,
} from 'antd';
import { FormInstance } from 'antd/lib/form';
import { PlusCircleOutlined, MinusCircleOutlined } from '@ant-design/icons';

import { OrgInfo, listOrgs } from '../api/Org';
import { serverValidateNetId } from '../Validators';

/**
 * The final values of the edit link form
 * @interface
 */
export interface EditLinkFormValues {
  /**
   * The new aliases
   * @property
   */
  aliases: { alias: string; description: string }[];
}

/**
 * Props of the [[ShareLinkModal]] component
 * @interface
 */
export interface Props {
  /**
   * Whether the modal is visible
   * @property
   */
  visible: boolean;

  /**
   * The user's privileges, used to determine whether the user
   * may create custom aliases
   * @property
   */
  userPrivileges: Set<string>;

  /**
   * List of netids/organizations who can edit the link
   * @property
   */
  people: Array<{ _id: string; type: string; permission: string }>;

  /**
   * Callback that will be called when the user clicks the "ok" button
   * @property
   */
  onOk: (values: EditLinkFormValues) => void;

  /**
   * Callback that will be called when the user closes the modal without
   * saving their changes
   * @property
   */
  onCancel: () => void;
}

/**
 * State of the [[ShareLinkModal]] component
 * @interface
 */
export interface State {
  /**
   * Equals "netid" when user is adding a netid, "org" when user is adding an org
   * @property
   */
  addNetIDOrOrg: string;

  /**
   * True when Modal is fetching data.
   * @property
   */
  isLoading: boolean;

  /**
   * Whether to show all orgs or just orgs of which the user is a member. Option only
   * available to admins
   * @property
   */
  showAll: boolean;

  /**
   * Contains an [[OrgInfo]] for each org to be displayed
   * @property
   */
  orgs: OrgInfo[];

  /**
   * The list of organizations for the editor/viewer dropdown
   * @property
   */
  options: { label: string; value: string }[];
}

/**
 * The [[ShareLinkModal]] component allows the user to edit the netIDs and organizations a link is shared with. The user may
 *   * Add or remove NetIDs to be editors/viewers
 *   * Add or remove Organizations to be editors/viewers
 * @param props The props
 */
export class ShareLinkModal extends React.Component<Props, State> {
  formRef = React.createRef<FormInstance>();

  tableColumns = [
    {
      title: 'NetID/Org',
      dataIndex: '_id',
    },
    {
      title: 'Type',
      dataIndex: 'type',
      render: (type: string) => (
        <>
          <Tag color={type == 'org' ? '#C70000' : 'red'}>{type}</Tag>
        </>
      ),
    },
    {
      title: 'Permission',
      dataIndex: 'permission',
      render: (permission: string) => (
        <>
          <Tag color={permission == 'editor' ? '#C70000' : 'red'}>
            {permission}
          </Tag>
        </>
      ),
    },
    {
      title: 'Remove',
      render: () => (
        <>
          <Button>
            <MinusCircleOutlined />
          </Button>
        </>
      ),
    },
  ];

  constructor(props: Props) {
    super(props);
    this.state = {
      addNetIDOrOrg: 'netid',
      isLoading: false,
      showAll: false,
      orgs: [],
      options: [],
    };
  }

  async componentDidMount(): Promise<void> {
    await this.refreshOrgs();
    var options = this.state.orgs.map((org) => {
      return { label: org.name, value: org.id };
    });
    this.setState({ options: options });
  }

  /**
   * Execute API requests to get list of org info, then update state
   * @method
   */
  refreshOrgs = async (): Promise<void> => {
    await listOrgs(this.state.showAll ? 'all' : 'user').then((orgs) =>
      this.setState({ orgs })
    );
  };

  addPeople(values: any) {
    console.log('values: ', values);
  }

  render(): React.ReactNode {
    return (
      <Modal
        visible={this.props.visible}
        title="Share link"
        okText="Done"
        okType="ghost"
        cancelButtonProps={{ style: { display: 'none' } }}
        onOk={() => {
          this.formRef.current!.resetFields();
          this.props.onCancel();
          // CALL /api/v1/link/<id>/acl modify_acl function
        }}
        onCancel={() => {
          this.formRef.current!.resetFields();
          this.props.onCancel();
        }}
      >
        <Table
          columns={this.tableColumns}
          dataSource={this.props.people}
          locale={{ emptyText: 'This link is not shared with anyone.' }}
          pagination={{
            total: this.props.people.length > 0 ? this.props.people.length : 1, // always shows pagination
          }}
        />
        <Form ref={this.formRef} onFinish={this.addPeople}>
          <Row gutter={8}>
            <Col span={14}>
              <Space>
                Add
                <Radio.Group
                  onChange={(e) =>
                    this.setState({ addNetIDOrOrg: e.target.value })
                  }
                  defaultValue="netid"
                  buttonStyle="solid"
                >
                  <Radio.Button value="netid">NetID</Radio.Button>
                  <Radio.Button value="org">Organization</Radio.Button>
                </Radio.Group>
                :
                <Col flex="auto" />
              </Space>
            </Col>
          </Row>

          <Row>
            <Col span={12}>
              {this.state.addNetIDOrOrg == 'netid' ? (
                <Form.Item
                  name="netid"
                  rules={[{ validator: serverValidateNetId }]}
                >
                  <Input placeholder="NetID" />
                </Form.Item>
              ) : (
                <Form.Item name="organization">
                  <Select placeholder="Select an organization" allowClear>
                    {this.state.orgs.map((org, index) => (
                      <Select.Option value={org.id} key={index}>
                        {org.name}
                      </Select.Option>
                    ))}
                  </Select>
                </Form.Item>
              )}
            </Col>
            <Col span={6}>
              <Form.Item name="permission_level" initialValue="viewer">
                <Select>
                  <Select.Option value="viewer">Viewer</Select.Option>
                  <Select.Option value="editor">Editor</Select.Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item>
                <Button type="primary" htmlType="submit">
                  <PlusCircleOutlined />
                  Share
                </Button>
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    );
  }
}
